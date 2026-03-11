from __future__ import annotations

import argparse
import concurrent.futures
import hmac
import http.client
import json
import os
import select
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from cdx_proxy_cli_v2.auth.store import load_auth_records
from cdx_proxy_cli_v2.auth.eligibility import (
    fetch_limit_health,
    merge_runtime_with_limits,
    merged_ok,
)
from cdx_proxy_cli_v2.observability.event_log import EventLogger
from cdx_proxy_cli_v2.proxy.rules import (
    CHATGPT_HOSTS,
    build_forward_headers,
    get_request_timeout,
    is_loopback_host,
    is_primary_responses_path,
    management_route,
    rewrite_request_path,
    set_header_case_insensitive,
    trace_route,
)
from cdx_proxy_cli_v2.auth.rotation import (
    CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE,
    RoundRobinAuthPool,
    is_auth_incompatible_error,
    is_retryable_auth_failure,
)
from cdx_proxy_cli_v2.config.settings import Settings, build_settings
from cdx_proxy_cli_v2.observability.trace_store import TraceStore
from cdx_proxy_cli_v2.proxy.overload import LocalOverloadGuard

DEFAULT_MAX_REQUEST_BODY = 10 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BODY = 10 * 1024 * 1024
CHATGPT_ACCOUNT_MODELS = (
    "gpt-5.1-codex-max",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
)
CHATGPT_ACCOUNT_MODEL_FALLBACK = CHATGPT_ACCOUNT_MODELS[0]
CHATGPT_ACCOUNT_MODEL_REWRITES = {
    "gpt-5.4": CHATGPT_ACCOUNT_MODEL_FALLBACK,
    "gpt-5.3-codex": CHATGPT_ACCOUNT_MODEL_FALLBACK,
    "gpt-5.2-codex": CHATGPT_ACCOUNT_MODEL_FALLBACK,
}
CHATGPT_ACCOUNT_INCOMPATIBLE_MARKERS = (
    "not supported when using codex with a chatgpt account",
    "not supported for codex with a chatgpt account",
)


def _extract_error_strings(raw_body: bytes) -> list[str]:
    if not raw_body:
        return []
    try:
        parsed = json.loads(raw_body.decode("utf-8", errors="replace"))
    except Exception:
        return []
    texts: list[str] = []
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            for key in ("code", "message", "detail", "type"):
                value = error.get(key)
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
        elif isinstance(error, str) and error.strip():
            texts.append(error.strip())
        for key in ("code", "message", "detail"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    return texts


def _extract_error_code(
    raw_body: bytes, *, status: Optional[int] = None
) -> Optional[str]:
    texts = _extract_error_strings(raw_body)
    if int(status or 0) == 400:
        haystack = " ".join(texts).lower()
        if any(marker in haystack for marker in CHATGPT_ACCOUNT_INCOMPATIBLE_MARKERS):
            return CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE
    for value in texts:
        if value and " " not in value:
            return value
    return None


def _header_value_case_insensitive(headers: Dict[str, str], key: str) -> str:
    for existing_key, value in headers.items():
        if existing_key.lower() == key.lower():
            return str(value)
    return ""


def _normalize_chatgpt_request_body(body: bytes, headers: Dict[str, str]) -> bytes:
    if not body:
        return body
    if "json" not in _header_value_case_insensitive(headers, "Content-Type").lower():
        return body
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return body
    if not isinstance(payload, dict):
        return body
    model = payload.get("model")
    if not isinstance(model, str):
        return body
    rewritten_model = CHATGPT_ACCOUNT_MODEL_REWRITES.get(model.strip())
    if not rewritten_model:
        return body
    payload["model"] = rewritten_model
    return json.dumps(payload).encode("utf-8")


def _is_models_request_path(path: str) -> bool:
    path_only = urlsplit(path or "").path.rstrip("/")
    return path_only in {"/models", "/backend-api/models"}


def _normalize_models_response_body(body: bytes, *, request_path: str) -> bytes:
    if not body or not _is_models_request_path(request_path):
        return body
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return body
    changed = False
    if isinstance(payload, dict):
        for key in ("models", "data"):
            models = payload.get(key)
            if not isinstance(models, list):
                continue
            for item in models:
                if not isinstance(item, dict):
                    continue
                if item.get("display_name"):
                    pass
                else:
                    display_name = (
                        item.get("title") or item.get("slug") or item.get("id")
                    )
                    if isinstance(display_name, str) and display_name.strip():
                        item["display_name"] = display_name
                        changed = True
                if not isinstance(item.get("supported_reasoning_levels"), list):
                    supported_reasoning_levels: list[str] = []
                    thinking_efforts = item.get("thinking_efforts")
                    if isinstance(thinking_efforts, list):
                        for effort in thinking_efforts:
                            if not isinstance(effort, dict):
                                continue
                            level = effort.get("thinking_effort")
                            if isinstance(level, str) and level.strip():
                                supported_reasoning_levels.append(level.strip())
                    item["supported_reasoning_levels"] = supported_reasoning_levels
                    changed = True
    if not changed:
        return body
    return json.dumps(payload).encode("utf-8")


@dataclass
class UpstreamAttemptResult:
    status: int
    headers: List[Tuple[str, str]]
    body: bytes
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    stream_response: Optional[http.client.HTTPResponse] = None
    stream_connection: Optional[http.client.HTTPConnection] = None
    websocket_upgrade: bool = False


@dataclass
class ProxyRuntime:
    settings: Settings
    auth_pool: RoundRobinAuthPool = field(init=False)
    trace_store: TraceStore = field(init=False)
    logger: EventLogger = field(init=False)
    overload_guard: LocalOverloadGuard = field(init=False)
    _auto_reset_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _metrics_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _auto_reset_blocked_until: float = field(default=0.0, init=False, repr=False)
    # Auto-heal background checker
    _auto_heal_thread: Optional[threading.Thread] = field(
        default=None, init=False, repr=False
    )
    _auto_heal_stop: threading.Event = field(
        default_factory=threading.Event, init=False, repr=False
    )
    _limit_health_cache: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, init=False, repr=False
    )
    _limit_health_cache_at: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.trace_store = TraceStore(max_size=self.settings.trace_max)
        self.logger = EventLogger(self.settings.auth_dir)
        self.overload_guard = LocalOverloadGuard(
            max_in_flight_requests=self.settings.max_in_flight_requests,
            max_pending_requests=self.settings.max_pending_requests,
        )
        self._metrics = {
            "requests_total": 0,
            "upstream_errors_total": 0,
            "auth_ejections_total": 0,
            "auth_restores_total": 0,
        }
        self._auto_heal_last_check: Dict[str, float] = {}
        # Initialize auth pool with settings
        self.auth_pool = RoundRobinAuthPool(
            auto_heal_interval=self.settings.auto_heal_interval,
            auto_heal_success_target=self.settings.auto_heal_success_target,
            auto_heal_max_attempts=self.settings.auto_heal_max_attempts,
            max_ejection_percent=self.settings.max_ejection_percent,
            consecutive_error_threshold=self.settings.consecutive_error_threshold,
        )
        # Start background auto-heal checker
        self._start_auto_heal_checker()

    def _refresh_limit_health(
        self, *, force: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        before_accounts = self._merged_accounts(limit_health=self._limit_health_cache)
        if (
            not force
            and self._limit_health_cache
            and (now - self._limit_health_cache_at) < 60.0
        ):
            return self._limit_health_cache
        try:
            self._limit_health_cache = fetch_limit_health(self.settings.auth_dir)
            self._limit_health_cache_at = now
        except Exception:
            # Keep last known limit view on fetch errors; runtime auth health still works.
            pass
        self.auth_pool.apply_limit_health(self._limit_health_cache)
        after_accounts = self._merged_accounts(limit_health=self._limit_health_cache)
        self._emit_auth_transitions(
            before_accounts=before_accounts, after_accounts=after_accounts
        )
        return self._limit_health_cache

    def _start_auto_heal_checker(self) -> None:
        """Start background thread for health checking blacklisted keys."""
        self._auto_heal_stop.clear()
        self._auto_heal_thread = threading.Thread(
            target=self._auto_heal_loop,
            daemon=True,
            name="auto-heal-checker",
        )
        self._auto_heal_thread.start()

    def _auto_heal_loop(self) -> None:
        """Background loop: check blacklisted keys and attempt auto-heal."""
        while not self._auto_heal_stop.is_set():
            try:
                self._run_auto_heal_cycle()
            except Exception:
                # Silently continue on errors, log at debug level only
                pass

            # Sleep for check interval
            self._auto_heal_stop.wait(timeout=self.auth_pool.auto_heal_interval)

    def _run_auto_heal_cycle(self, *, now: Optional[float] = None) -> None:
        """Run one auto-heal scan over blacklist/probation keys."""
        now_ts = float(now if now is not None else time.time())
        snapshot = self.auth_pool.health_snapshot()

        for account in snapshot:
            status = str(account.get("status") or "").upper()
            if status not in {"BLACKLIST", "PROBATION"}:
                continue
            if (
                account.get("blacklist_reason")
                == CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE
            ):
                continue

            auth_file = str(account.get("file") or "").strip()
            if not auth_file:
                continue

            last_check = self._auto_heal_last_check.get(auth_file, 0.0)
            if now_ts - last_check < self.auth_pool.auto_heal_interval:
                continue

            next_probe_at = account.get("until")
            if (
                status == "PROBATION"
                and isinstance(next_probe_at, (int, float))
                and now_ts < float(next_probe_at)
            ):
                continue

            success = self._perform_auto_heal_check(account)
            self._auto_heal_last_check[auth_file] = now_ts

            if success:
                # Reload before restoration so fresh on-disk tokens are used.
                self.reload_auths()
                self.apply_auth_result(auth_file, status=200)
                merged_state = {
                    item.get("file", ""): item
                    for item in self.health_snapshot(refresh=False).get("accounts", [])
                }.get(auth_file, {})
                if bool(merged_state.get("eligible_now")):
                    self._notify_user(
                        level="INFO",
                        event="auto_heal.success",
                        message=f"Key {account.get('email') or auth_file} restored after successful health check",
                        auth_file=auth_file,
                        auth_email=account.get("email"),
                    )
                else:
                    self._notify_user(
                        level="INFO",
                        event="auto_heal.progress",
                        message=f"Health check passed for {account.get('email') or auth_file}, waiting for full re-entry",
                        auth_file=auth_file,
                        auth_email=account.get("email"),
                    )
                continue

            if status == "BLACKLIST":
                self.auth_pool.mark_auto_heal_failure(auth_file, now_ts)

            state = {
                item.get("file", ""): item for item in self.auth_pool.health_snapshot()
            }.get(auth_file, {})
            self._notify_user(
                level="WARN",
                event="auto_heal.failure",
                message=f"Health check failed for {account.get('email') or auth_file}, blacklist extended",
                auth_file=auth_file,
                auth_email=account.get("email"),
                cooldown_seconds=state.get("cooldown_seconds"),
                blacklist_seconds=state.get("blacklist_seconds"),
            )

    def _perform_auto_heal_check(self, account: Dict[str, Any]) -> bool:
        """Perform a lightweight health check on a blacklisted key.

        Returns True if the key appears to be working again.
        """

        auth_file = account.get("file", "")
        matching_record = None
        for candidate in load_auth_records(self.settings.auth_dir):
            if candidate.name == auth_file:
                matching_record = candidate
                break
        if matching_record is None or not matching_record.token:
            return False

        result = self._probe_single_auth(
            auth_file,
            matching_record.token,
            matching_record.account_id,
            timeout=5,
        )
        return result.get("success", False)

    def _probe_single_auth(
        self,
        auth_file: str,
        token: str,
        account_id: Optional[str] = None,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """Probe a single auth key via HTTP GET to /backend-api/models.

        Returns a dict with probe results including success status,
        http_status, latency, and error information.
        """
        import http.client
        from urllib.parse import urlsplit

        start_time = time.time()
        result: Dict[str, Any] = {
            "file": auth_file,
            "success": False,
            "http_status": None,
            "error_code": None,
            "latency_ms": 0,
        }

        try:
            parsed = urlsplit(self.settings.upstream)
            host = parsed.hostname or "chatgpt.com"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            base_path = parsed.path.rstrip("/")
            path = f"{base_path}/models" if base_path else "/models"
            chatgpt_backend = (
                host.lower() in CHATGPT_HOSTS and base_path == "/backend-api"
            )
            headers = build_forward_headers({}, chatgpt_backend=chatgpt_backend)
            set_header_case_insensitive(headers, "Authorization", f"Bearer {token}")
            set_header_case_insensitive(headers, "Content-Type", "application/json")
            if chatgpt_backend and account_id:
                set_header_case_insensitive(
                    headers, "ChatGPT-Account-Id", str(account_id)
                )

            conn_cls = (
                http.client.HTTPSConnection
                if parsed.scheme == "https"
                else http.client.HTTPConnection
            )
            conn = conn_cls(host, port, timeout=timeout)
            try:
                conn.request(
                    "GET",
                    path,
                    headers=headers,
                )
                response = conn.getresponse()
                result["http_status"] = response.status
                result["latency_ms"] = int((time.time() - start_time) * 1000)

                # Read and classify body
                try:
                    raw_body = response.read()
                except Exception:
                    raw_body = b""
                extracted_error_code = _extract_error_code(
                    raw_body, status=response.status
                )

                # Determine success based on status code
                if 200 <= response.status < 300:
                    result["success"] = True
                elif response.status in {401, 403}:
                    result["error_code"] = extracted_error_code or (
                        "token_invalid" if response.status == 401 else "forbidden"
                    )
                elif response.status == 429:
                    result["error_code"] = extracted_error_code or "rate_limited"
                elif response.status >= 500:
                    result["error_code"] = extracted_error_code or "server_error"
                else:
                    result["error_code"] = (
                        extracted_error_code or f"http_{response.status}"
                    )

            finally:
                conn.close()

        except Exception as exc:
            result["latency_ms"] = int((time.time() - start_time) * 1000)
            result["error_code"] = "network_error"
            result["error"] = str(exc)

        return result

    def probe_all_auths(self, timeout: int = 10) -> Dict[str, Any]:
        """Probe all auth keys without mutating their current runtime state.

        Returns a summary of probe results with per-key details.
        """
        records = load_auth_records(self.settings.auth_dir)
        if not records:
            return {
                "probed": 0,
                "results": [],
            }

        # Get current snapshot for comparison
        snapshot_before = {
            item.get("file", ""): item for item in self.auth_pool.health_snapshot()
        }

        results: List[Dict[str, Any]] = []

        # Use ThreadPoolExecutor to probe keys in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_record = {
                executor.submit(
                    self._probe_single_auth,
                    record.name,
                    record.token,
                    record.account_id,
                    timeout,
                ): record
                for record in records
            }

            for future in concurrent.futures.as_completed(future_to_record):
                record = future_to_record[future]
                try:
                    probe_result = future.result()
                except Exception as exc:
                    probe_result = {
                        "file": record.name,
                        "success": False,
                        "http_status": None,
                        "error_code": "probe_exception",
                        "latency_ms": 0,
                        "error": str(exc),
                    }

                # Get previous status
                prev_state = snapshot_before.get(record.name, {})
                prev_status = prev_state.get("status", "UNKNOWN")

                # Determine action without mutating runtime state.
                http_status = probe_result.get("http_status")
                error_code = probe_result.get("error_code")

                if probe_result.get("success"):
                    action = "healthy"
                elif http_status == 429:
                    action = "would_cooldown"
                elif http_status in {401, 403}:
                    action = "auth_failed"
                elif is_auth_incompatible_error(
                    int(http_status or 0), str(error_code or "")
                ):
                    action = "compat_failed"
                elif http_status is not None:
                    action = "error"
                else:
                    action = "network_error"

                results.append(
                    {
                        "file": record.name,
                        "email": record.email,
                        "previous_status": prev_status,
                        "status": prev_status,
                        "http_status": http_status,
                        "action": action,
                        "latency_ms": probe_result.get("latency_ms", 0),
                        "error": probe_result.get("error") or error_code,
                    }
                )

        return {
            "probed": len(results),
            "results": results,
        }

    def _notify_user(
        self,
        *,
        level: str,
        event: str,
        message: str,
        **kwargs: Any,
    ) -> None:
        """Send notification to user via logger and trace store."""
        # Remove 'event' from kwargs if present to avoid duplication
        kwargs.pop("event", None)
        payload = {
            "ts": time.time(),
            "event": event,
            "message": message,
            **kwargs,
        }
        self.trace_store.add(payload)
        self.logger.write(level=level, event=event, message=message, **kwargs)

    def _merged_accounts(
        self,
        *,
        limit_health: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        active_limit_health = (
            self._limit_health_cache if limit_health is None else limit_health
        )
        return merge_runtime_with_limits(
            self.auth_pool.health_snapshot(), active_limit_health
        )

    @staticmethod
    def _account_index(accounts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        for account in accounts:
            if not isinstance(account, dict):
                continue
            auth_file = str(account.get("file") or "").strip()
            if auth_file:
                indexed[auth_file] = account
        return indexed

    def _increment_metric(self, key: str, amount: int = 1) -> None:
        with self._metrics_lock:
            self._metrics[key] = int(self._metrics.get(key, 0)) + int(amount)

    def metrics_snapshot(self) -> Dict[str, int]:
        with self._metrics_lock:
            counters = dict(self._metrics)
        counters.update(self.overload_guard.snapshot())
        counters["auth_available"] = sum(
            1
            for account in self._merged_accounts(limit_health=self._limit_health_cache)
            if bool(account.get("eligible_now"))
        )
        return counters

    def _emit_auth_transitions(
        self,
        *,
        before_accounts: List[Dict[str, Any]],
        after_accounts: List[Dict[str, Any]],
        trigger_status: Optional[int] = None,
        error_code: Optional[str] = None,
    ) -> None:
        before_by_file = self._account_index(before_accounts)
        after_by_file = self._account_index(after_accounts)
        for auth_file in sorted(set(before_by_file.keys()) | set(after_by_file.keys())):
            before = before_by_file.get(auth_file, {})
            after = after_by_file.get(auth_file, {})
            before_status = str(before.get("status") or "UNKNOWN").upper()
            after_status = str(after.get("status") or "UNKNOWN").upper()
            before_eligible = bool(before.get("eligible_now"))
            after_eligible = bool(after.get("eligible_now"))
            before_reason_origin = str(before.get("reason_origin") or "").strip()
            after_reason_origin = str(after.get("reason_origin") or "").strip()

            event: Optional[str] = None
            level = "INFO"
            if after_status == "BLACKLIST" and before_status != "BLACKLIST":
                event = "auth.ejected"
                level = "WARN"
                self._increment_metric("auth_ejections_total")
            elif after_status == "COOLDOWN" and after_reason_origin == "limit":
                if before_status != "COOLDOWN" or before_reason_origin != "limit":
                    event = "auth.limit_blocked"
            elif after_status == "COOLDOWN" and before_status != "COOLDOWN":
                event = "auth.cooldown"
            elif after_status == "PROBATION" and before_status != "PROBATION":
                event = "auth.probation"
            elif after_eligible and not before_eligible and before_status != "UNKNOWN":
                event = "auth.returned"
                self._increment_metric("auth_restores_total")

            if not event:
                continue

            auth_email = after.get("email") or before.get("email")
            display_name = auth_email or auth_file
            reason = (
                after.get("reason")
                or after.get("blacklist_reason")
                or after.get("limit_reason")
            )
            self._notify_user(
                level=level,
                event=event,
                message=f"Auth {display_name} moved to {after_status.lower()}",
                auth_file=auth_file,
                auth_email=auth_email,
                before_status=before_status,
                after_status=after_status,
                reason=reason,
                reason_origin=after_reason_origin or None,
                trigger_status=trigger_status,
                error_code=error_code,
            )

    def apply_auth_result(
        self,
        auth_name: str,
        *,
        status: int,
        error_code: Optional[str] = None,
        cooldown_seconds: Optional[int] = None,
    ) -> None:
        before_accounts = self._merged_accounts(limit_health=self._limit_health_cache)
        self.auth_pool.mark_result(
            auth_name,
            status=status,
            error_code=error_code,
            cooldown_seconds=cooldown_seconds,
        )
        after_accounts = self._merged_accounts(limit_health=self._limit_health_cache)
        self._emit_auth_transitions(
            before_accounts=before_accounts,
            after_accounts=after_accounts,
            trigger_status=status,
            error_code=error_code,
        )

    def shutdown(self) -> None:
        """Shutdown runtime and stop background threads."""
        self._auto_heal_stop.set()
        if self._auto_heal_thread:
            self._auto_heal_thread.join(timeout=2.0)

    def reload_auths(self) -> int:
        records = load_auth_records(self.settings.auth_dir)
        self.auth_pool.load(records)
        return len(records)

    def health_snapshot(self, *, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            self.reload_auths()
        self._refresh_limit_health(force=refresh)
        accounts = self._merged_accounts(limit_health=self._limit_health_cache)
        return {
            "ok": merged_ok(accounts),
            "accounts": accounts,
        }

    def trace_events(self, limit: int) -> List[Dict[str, Any]]:
        return self.trace_store.list(limit=limit)

    def debug_payload(self, host: str, port: int) -> Dict[str, Any]:
        return {
            "status": "running",
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
            "auth_dir": self.settings.auth_dir,
            "auth_count": self.auth_pool.count(),
            "upstream_base_url": self.settings.upstream,
            "log_request_preview": False,
            "management_key_required": bool(self.settings.management_key),
            "trace_max": self.trace_store.max_size,
            "request_timeout": self.settings.request_timeout,
            "compact_timeout": self.settings.compact_timeout,
            "max_in_flight_requests": self.settings.max_in_flight_requests,
            "max_pending_requests": self.settings.max_pending_requests,
            "auto_reset_on_single_key": self.settings.auto_reset_on_single_key,
            "auto_reset_streak": self.settings.auto_reset_streak,
            "auto_reset_cooldown": self.settings.auto_reset_cooldown,
            "pid": os.getpid(),
            "event_log_file": str(self.logger.path),
            "metrics": self.metrics_snapshot(),
        }

    def record_attempt(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        route: str,
        status: int,
        latency_ms: int,
        auth_name: str,
        auth_email: Optional[str],
        attempt: int,
        client_ip: Optional[str],
        error: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "ts": time.time(),
            "event": "proxy.request",
            "request_id": request_id,
            "method": method,
            "path": path,
            "route": route,
            "status": status,
            "latency_ms": latency_ms,
            "auth_file": auth_name,
            "auth_email": auth_email,
            "attempt": attempt,
            "client_ip": client_ip,
        }
        if error:
            payload["error"] = error
        self.trace_store.add(payload)
        log_payload = dict(payload)
        log_payload.pop("event", None)
        self.logger.write(
            level="INFO" if status < 500 else "WARN",
            event="proxy.request",
            message="request attempt completed",
            **log_payload,
        )

    def maybe_auto_reset_single_key_stall(self) -> int:
        """Recover blacklisted/probation auths after a sustained single-key streak.

        This is intentionally opt-in because it relaxes the default hard-failure
        isolation policy for 401/403 keys.
        """
        if not self.settings.auto_reset_on_single_key:
            return 0

        threshold = max(1, int(self.settings.auto_reset_streak))
        trace_events = self.trace_store.list(limit=self.trace_store.max_size)
        recent_events = [
            event
            for event in reversed(trace_events)
            if str(event.get("event") or "") == "proxy.request"
        ][:threshold]
        if len(recent_events) < threshold:
            return 0

        auth_names = {
            str(event.get("auth_file") or "").strip()
            for event in recent_events
            if str(event.get("auth_file") or "").strip()
        }
        if len(auth_names) != 1:
            return 0

        stats = self.auth_pool.stats()
        if int(stats.get("total", 0)) < 2:
            return 0
        if int(stats.get("ok", 0)) != 1:
            return 0
        recoverable = int(stats.get("blacklist", 0)) + int(stats.get("probation", 0))
        if recoverable <= 0:
            return 0

        now = time.time()
        with self._auto_reset_lock:
            if now < self._auto_reset_blocked_until:
                return 0

            reset_count = self.auth_pool.reset_auth(state="blacklist")
            reset_count += self.auth_pool.reset_auth(state="probation")
            if reset_count <= 0:
                return 0

            self._auto_reset_blocked_until = now + max(
                1, int(self.settings.auto_reset_cooldown)
            )
            only_auth = next(iter(auth_names))
            self.logger.write(
                level="WARN",
                event="proxy.auth_auto_reset",
                message="auto-reset blacklist/probation keys after single-key streak",
                trigger_auth=only_auth,
                streak=threshold,
                cooldown_seconds=self.settings.auto_reset_cooldown,
                reset=reset_count,
            )
            return reset_count


class ProxyHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: Tuple[str, int], runtime: ProxyRuntime):
        super().__init__(server_address, ProxyHandler)
        self.runtime = runtime

    def initiate_shutdown(self) -> None:
        threading.Thread(target=self.shutdown, daemon=True).start()


class ProxyHandler(BaseHTTPRequestHandler):
    server: ProxyHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    @staticmethod
    def _is_websocket_upgrade_request(headers: Dict[str, str]) -> bool:
        upgrade = _header_value_case_insensitive(headers, "Upgrade").strip().lower()
        connection = (
            _header_value_case_insensitive(headers, "Connection").strip().lower()
        )
        if upgrade != "websocket":
            return False
        connection_tokens = {
            token.strip() for token in connection.split(",") if token.strip()
        }
        return "upgrade" in connection_tokens

    def _tunnel_websocket(
        self,
        *,
        upstream_connection: http.client.HTTPConnection,
        upstream_response: http.client.HTTPResponse,
    ) -> None:
        upstream_socket = getattr(upstream_connection, "sock", None)
        client_socket = self.connection
        if upstream_socket is None:
            raise RuntimeError("upstream websocket socket unavailable")

        self.close_connection = True
        try:
            self.wfile.flush()
        except Exception:
            pass

        sockets = [client_socket, upstream_socket]
        try:
            for sock in sockets:
                try:
                    sock.settimeout(None)
                except Exception:
                    pass

            while True:
                readable, _, exceptional = select.select(sockets, [], sockets)
                if exceptional:
                    break
                for source in readable:
                    try:
                        chunk = source.recv(65536)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        return
                    target = (
                        upstream_socket if source is client_socket else client_socket
                    )
                    target.sendall(chunk)
        finally:
            try:
                upstream_response.close()
            except Exception:
                pass
            try:
                upstream_connection.close()
            except Exception:
                pass

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

    def do_PUT(self) -> None:  # noqa: N802
        self._handle_request()

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle_request()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle_request()

    def _handle_request(self) -> None:
        route = management_route(self.path)
        if route:
            if not self._authorize_management():
                self._send_json(401, {"error": "unauthorized management request"})
                return
            self._handle_management(route)
            return
        self._proxy_request()

    def _handle_models_endpoint(self) -> None:
        """Compatibility helper for tests and direct local probes."""
        models_response = {
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "owned_by": "openai",
                    "display_name": model_id,
                }
                for model_id in CHATGPT_ACCOUNT_MODELS
            ]
        }
        self._send_json(200, models_response)

    def _authorize_management(self) -> bool:
        expected = str(self.server.runtime.settings.management_key or "")
        if not expected:
            return True
        provided = str(self.headers.get("X-Management-Key") or "")
        return hmac.compare_digest(provided, expected)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected before body flush; keep server alive without noisy traceback.
            return

    def _read_body(self) -> Optional[bytes]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except (ValueError, OverflowError):
            self._send_json(400, {"error": "invalid content length"})
            return None
        if length < 0:
            self._send_json(400, {"error": "invalid content length"})
            return None
        if length == 0:
            return b""
        if length > DEFAULT_MAX_REQUEST_BODY:
            self._send_json(413, {"error": "request body too large"})
            return None
        return self.rfile.read(length)

    def _query_params(self) -> Dict[str, List[str]]:
        query = urlsplit(self.path).query
        if not query:
            return {}
        return parse_qs(query)

    def _first_query_value(
        self, params: Dict[str, List[str]], key: str
    ) -> Optional[str]:
        values = params.get(key)
        if not values:
            return None
        return values[0]

    def _int_query_value(
        self, params: Dict[str, List[str]], key: str, default: int = 0
    ) -> int:
        raw_value = self._first_query_value(params, key)
        if raw_value is None:
            return default
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return default

    def _parse_reset_params(
        self, params: Dict[str, List[str]]
    ) -> tuple[Optional[str], Optional[str]]:
        """Parse reset query parameters from request path.

        Returns:
            Tuple of (name, state) filters. Either may be None.
        """
        name = self._first_query_value(params, "name")
        state = self._first_query_value(params, "state")
        return name, state

    def _handle_management(self, route: str) -> None:
        host, port = self.server.server_address[:2]
        runtime = self.server.runtime
        params = self._query_params()
        if route == "debug":
            self._send_json(200, runtime.debug_payload(host=str(host), port=int(port)))
            return
        if route == "trace":
            limit = self._int_query_value(params, "limit", default=0)
            self._send_json(200, {"events": runtime.trace_events(limit=limit)})
            return
        if route == "health":
            refresh = self._first_query_value(params, "refresh") == "1"
            self._send_json(200, runtime.health_snapshot(refresh=refresh))
            return
        if route == "auth-files":
            self._send_json(200, {"files": runtime.auth_pool.auth_files()})
            return
        if route == "shutdown":
            self._send_json(200, {"status": "shutting_down"})
            runtime.logger.write(
                level="INFO",
                event="proxy.shutdown_requested",
                message="shutdown requested",
            )
            self.server.initiate_shutdown()
            return
        if route == "reset":
            if self.command.upper() != "POST":
                self._send_json(405, {"error": "Method not allowed. Use POST."})
                return
            name, state = self._parse_reset_params(params)
            count = runtime.auth_pool.reset_auth(name=name, state=state)
            self._send_json(
                200, {"reset": count, "filter": {"name": name, "state": state}}
            )
            runtime.logger.write(
                level="INFO",
                event="proxy.auth_reset",
                message=f"reset {count} auth key(s)",
                name=name,
                state=state,
                count=count,
            )
            return
        if route == "probe":
            if self.command.upper() != "POST":
                self._send_json(405, {"error": "Method not allowed. Use POST."})
                return
            # Parse timeout param (default 10, min 1, max 30)
            timeout = self._int_query_value(params, "timeout", default=10)
            timeout = max(1, min(30, timeout))

            # Perform probe
            probe_result = runtime.probe_all_auths(timeout=timeout)

            # Log probe event
            actions = {}
            for r in probe_result.get("results", []):
                action = r.get("action", "none")
                actions[action] = actions.get(action, 0) + 1

            runtime.logger.write(
                level="INFO",
                event="proxy.probe",
                message=f"probed {probe_result['probed']} auth key(s)",
                probed=probe_result["probed"],
                actions=actions,
            )

            self._send_json(200, probe_result)
            return
        self._send_json(404, {"error": "unknown management route"})

    def _run_upstream_attempt(
        self,
        *,
        scheme: str,
        host: str,
        port: int,
        rewritten_path: str,
        full_path: str,
        body: bytes,
        headers: Dict[str, str],
        request_timeout: int,
        compact_timeout: int,
    ) -> UpstreamAttemptResult:
        connection: Optional[http.client.HTTPConnection] = None
        try:
            conn_cls = (
                http.client.HTTPSConnection
                if scheme == "https"
                else http.client.HTTPConnection
            )
            timeout = get_request_timeout(
                rewritten_path,
                default=request_timeout,
                compact=compact_timeout,
            )
            connection = conn_cls(host, port, timeout=timeout)
            # Force HTTP/1.1 for proper keep-alive and streaming behavior
            connection._http_vsn = 11  # type: ignore[attr-defined]
            connection._http_vsn_str = "HTTP/1.1"  # type: ignore[attr-defined]
            connection.request(self.command, full_path, body=body, headers=headers)
            response = connection.getresponse()
            status = response.status
            response_headers = response.getheaders()
            upgrade_header = str(response.getheader("Upgrade") or "")
            if status == 101 and upgrade_header.lower() == "websocket":
                stream_connection = connection
                connection = None
                return UpstreamAttemptResult(
                    status=status,
                    headers=response_headers,
                    body=b"",
                    stream_response=response,
                    stream_connection=stream_connection,
                    websocket_upgrade=True,
                )
            content_type = str(response.getheader("Content-Type") or "")
            if "text/event-stream" in content_type.lower():
                stream_connection = connection
                connection = None
                return UpstreamAttemptResult(
                    status=status,
                    headers=response_headers,
                    body=b"",
                    stream_response=response,
                    stream_connection=stream_connection,
                )

            data = response.read(DEFAULT_MAX_RESPONSE_BODY + 1)
            if len(data) > DEFAULT_MAX_RESPONSE_BODY:
                return UpstreamAttemptResult(
                    status=413,
                    headers=[("Content-Type", "application/json")],
                    body=json.dumps({"error": "response body too large"}).encode(
                        "utf-8"
                    ),
                )
            data = _normalize_models_response_body(data, request_path=rewritten_path)

            return UpstreamAttemptResult(
                status=status,
                headers=response_headers,
                body=data,
                error_code=_extract_error_code(data, status=status),
            )
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            return UpstreamAttemptResult(
                status=502,
                headers=[("Content-Type", "application/json")],
                body=json.dumps(
                    {"error": "upstream request failed", "detail": error_message}
                ).encode("utf-8"),
                error_message=error_message,
                error_code="upstream_request_failed",
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _proxy_request(self) -> None:
        runtime = self.server.runtime
        runtime._increment_metric("requests_total")
        with runtime.overload_guard.acquire() as lease:
            if not lease.admitted:
                snapshot = runtime.overload_guard.snapshot()
                runtime._notify_user(
                    level="WARN",
                    event="proxy.overloaded",
                    message="proxy rejected request due to local overload",
                    **snapshot,
                )
                self._send_json(503, {"error": "proxy overloaded", **snapshot})
                return

            runtime._refresh_limit_health()
            upstream = urlsplit(runtime.settings.upstream)
            scheme = upstream.scheme or "https"
            host = upstream.hostname
            if not host:
                self._send_json(500, {"error": "invalid upstream host"})
                return
            port = upstream.port or (443 if scheme == "https" else 80)
            base_path = upstream.path.rstrip("/")

            incoming_path = self.path if self.path.startswith("/") else f"/{self.path}"
            route = trace_route(incoming_path)
            rewritten_path = rewrite_request_path(
                req_path=incoming_path,
                upstream_host=host,
                upstream_base_path=base_path,
            )
            if base_path and rewritten_path.startswith(f"{base_path}/"):
                full_path = rewritten_path
            else:
                full_path = (
                    f"{base_path}{rewritten_path}" if base_path else rewritten_path
                )

            chatgpt_backend = (
                host.lower() in CHATGPT_HOSTS
                and base_path.rstrip("/") == "/backend-api"
            )
            chatgpt_responses_mode = bool(
                chatgpt_backend and is_primary_responses_path(rewritten_path)
            )
            websocket_upgrade_request = (
                self.command.upper() == "GET"
                and self._is_websocket_upgrade_request(dict(self.headers))
            )

            body = self._read_body()
            if body is None:
                return
            if chatgpt_responses_mode:
                body = _normalize_chatgpt_request_body(body, dict(self.headers))

            base_headers = build_forward_headers(
                dict(self.headers),
                chatgpt_backend=chatgpt_backend,
                chatgpt_responses_mode=chatgpt_responses_mode,
                websocket_upgrade=websocket_upgrade_request,
            )

            max_attempts = max(1, runtime.auth_pool.count())
            compact_timeout = runtime.settings.compact_timeout
            request_id = uuid.uuid4().hex[:12]
            client_ip = self.client_address[0] if self.client_address else None

            final_status = 503
            final_headers: List[Tuple[str, str]] = [
                ("Content-Type", "application/json")
            ]
            final_body = json.dumps({"error": "no auths available"}).encode("utf-8")
            stream_response: Optional[http.client.HTTPResponse] = None
            stream_connection: Optional[http.client.HTTPConnection] = None
            final_websocket_upgrade = False
            auth_state = None

            attempt = 0
            while attempt < max_attempts:
                auth_state = runtime.auth_pool.pick()
                if not auth_state:
                    break

                headers = dict(base_headers)
                set_header_case_insensitive(
                    headers, "Authorization", f"Bearer {auth_state.record.token}"
                )
                if chatgpt_backend and auth_state.record.account_id:
                    set_header_case_insensitive(
                        headers, "chatgpt-account-id", str(auth_state.record.account_id)
                    )

                start = time.time()
                attempt_result = self._run_upstream_attempt(
                    scheme=scheme,
                    host=host,
                    port=port,
                    rewritten_path=rewritten_path,
                    full_path=full_path,
                    body=body,
                    headers=headers,
                    request_timeout=runtime.settings.request_timeout,
                    compact_timeout=compact_timeout,
                )
                latency_ms = int((time.time() - start) * 1000)

                final_status = attempt_result.status
                final_headers = attempt_result.headers
                final_body = attempt_result.body
                stream_response = attempt_result.stream_response
                stream_connection = attempt_result.stream_connection
                final_websocket_upgrade = attempt_result.websocket_upgrade

                runtime.record_attempt(
                    request_id=request_id,
                    method=self.command,
                    path=self.path,
                    route=route,
                    status=final_status,
                    latency_ms=latency_ms,
                    auth_name=auth_state.record.name,
                    auth_email=auth_state.record.email,
                    attempt=attempt + 1,
                    client_ip=client_ip,
                    error=attempt_result.error_message,
                )
                runtime.apply_auth_result(
                    auth_state.record.name,
                    status=final_status,
                    error_code=attempt_result.error_code,
                )
                runtime.maybe_auto_reset_single_key_stall()

                if is_retryable_auth_failure(final_status, attempt_result.error_code):
                    attempt += 1
                    if attempt < max_attempts:
                        continue
                break

            if auth_state is not None and final_status >= 500:
                runtime._increment_metric("upstream_errors_total")

            self.send_response(final_status)
            for key, value in final_headers:
                normalized = key.lower()
                if normalized in {"transfer-encoding", "content-length"}:
                    continue
                if normalized == "connection" and not final_websocket_upgrade:
                    continue
                self.send_header(key, value)

            if (
                final_websocket_upgrade
                and stream_response is not None
                and stream_connection is not None
            ):
                self.end_headers()
                self._tunnel_websocket(
                    upstream_connection=stream_connection,
                    upstream_response=stream_response,
                )
                return

            if stream_response is not None:
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        chunk = stream_response.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                finally:
                    try:
                        stream_response.close()
                    except Exception:
                        pass
                    if stream_connection is not None:
                        try:
                            stream_connection.close()
                        except Exception:
                            pass
                return

            if final_status == 503 and not auth_state:
                stats = runtime.auth_pool.stats()
                runtime._notify_user(
                    level="ERROR",
                    event="auth.pool_exhausted",
                    message=f"All auth keys unavailable (ok={stats['ok']}, cooldown={stats['cooldown']}, blacklist={stats['blacklist']})",
                    stats=stats,
                )

            self.send_header("Content-Length", str(len(final_body)))
            self.end_headers()
            if final_body:
                self.wfile.write(final_body)


def run_proxy_server(settings: Settings) -> None:
    if not is_loopback_host(settings.host) and not settings.allow_non_loopback:
        raise ValueError(
            "non-loopback bind blocked; use --allow-non-loopback to override"
        )
    management_key = str(settings.management_key or "").strip()
    if not management_key:
        raise ValueError("management key required")

    runtime = ProxyRuntime(settings=settings.with_management_key(management_key))
    auth_count = runtime.reload_auths()
    if auth_count <= 0:
        raise ValueError(f"no valid auth files found in {settings.auth_dir}")

    server = ProxyHTTPServer((settings.host, settings.port), runtime)
    bound_host, bound_port = server.server_address[:2]
    runtime.logger.write(
        level="INFO",
        event="proxy.started",
        message="proxy server started",
        host=bound_host,
        port=bound_port,
        upstream=settings.upstream,
        auth_count=auth_count,
    )

    stop_requested = False

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        if stop_requested:
            return
        stop_requested = True
        server.initiate_shutdown()

    previous_sigterm = signal.getsignal(signal.SIGTERM)
    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)
        runtime.shutdown()  # Stop background threads
        runtime.logger.write(
            level="INFO",
            event="proxy.stopped",
            message="proxy server stopped",
            host=bound_host,
            port=bound_port,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="cdx_proxy_cli_v2 proxy server")
    parser.add_argument("--auth-dir", required=False)
    parser.add_argument("--host", required=False)
    parser.add_argument("--port", type=int, required=False)
    parser.add_argument("--upstream", required=False)
    parser.add_argument("--management-key", required=False)
    parser.add_argument("--trace-max", type=int, required=False)
    parser.add_argument(
        "--request-timeout",
        type=int,
        required=False,
        help="Timeout in seconds for /responses endpoints (default: 45)",
    )
    parser.add_argument(
        "--compact-timeout",
        type=int,
        required=False,
        help="Timeout in seconds for /compact endpoints (default: 120)",
    )
    parser.add_argument("--allow-non-loopback", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = build_settings(
        auth_dir=args.auth_dir,
        host=args.host,
        port=args.port,
        upstream=args.upstream,
        management_key=args.management_key,
        allow_non_loopback=bool(args.allow_non_loopback),
        trace_max=args.trace_max,
        request_timeout=args.request_timeout,
        compact_timeout=args.compact_timeout,
    )
    run_proxy_server(settings)
    return 0
