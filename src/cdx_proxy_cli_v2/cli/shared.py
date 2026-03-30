"""Shared helpers for cdx CLI commands."""

from __future__ import annotations

import argparse
import shlex
import sys
from typing import Any, Dict, List, Optional

from cdx_proxy_cli_v2.auth.store import extract_auth_fields, read_auth_json
from cdx_proxy_cli_v2.cli.doctor_view import _extract_accounts
from cdx_proxy_cli_v2.cli.fs import _get_codex_home
from cdx_proxy_cli_v2.config.settings import Settings, build_settings, format_shell_exports
from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.runtime.service import service_status

DOCTOR_HEALTH_TIMEOUT_SECONDS = 8.0
ROTATE_HEALTH_TIMEOUT_SECONDS = 2.5
DOCTOR_POLICY = {
    "hard_fail_blacklist": [401, 403],
    "rate_limit_cooldown": 429,
    "probation_success_target": 2,
}


def _settings_from_args(args: argparse.Namespace) -> Settings:
    return build_settings(
        auth_dir=getattr(args, "auth_dir", None),
        host=getattr(args, "host", None),
        port=getattr(args, "port", None),
        upstream=getattr(args, "upstream", None),
        management_key=getattr(args, "management_key", None),
        allow_non_loopback=getattr(args, "allow_non_loopback", None),
        trace_max=getattr(args, "trace_max", None),
        request_timeout=getattr(args, "request_timeout", None),
        limit_min_remaining_percent=getattr(args, "limit_min_remaining_percent", None),
        max_in_flight_requests=getattr(args, "max_in_flight_requests", None),
        max_pending_requests=getattr(args, "max_pending_requests", None),
        auto_reset_on_single_key=getattr(args, "auto_reset_on_single_key", None),
        auto_reset_streak=getattr(args, "auto_reset_streak", None),
        auto_reset_cooldown=getattr(args, "auto_reset_cooldown", None),
    )


def _proxy_exports(
    settings: Settings, *, base_url: str, host: str, port: int
) -> Dict[str, str]:
    return {
        "CLIPROXY_BASE_URL": base_url,
        "OPENAI_API_BASE": base_url,
        "CLIPROXY_AUTH_DIR": settings.auth_dir,
        "CLIPROXY_ENV_FILE": str(settings.env_path),
        "CLIPROXY_HOST": host,
        "CLIPROXY_PORT": str(port),
    }


def _proxy_shell_setup(exports: Dict[str, str]) -> str:
    base_url = exports["CLIPROXY_BASE_URL"]
    return (
        f"{format_shell_exports(exports)}\n"
        "codex() {\n"
        '  env -u OPENAI_BASE_URL -u OPENAI_API_BASE command codex \\\n'
        f'    -c "openai_base_url=\\"{base_url}\\"" "$@"\n'
        "}\n"
    )


def _management_headers(settings: Settings) -> Dict[str, str]:
    key = str(settings.management_key or "").strip()
    if not key:
        return {}
    return {"X-Management-Key": key}


def _proxy_eval_hint(settings: Settings) -> str:
    auth_dir = shlex.quote(settings.auth_dir)
    return f'eval "$(cdx proxy --auth-dir {auth_dir} --print-env-only)"'


def _load_codex_auth_identity() -> tuple[Optional[str], Optional[str], Optional[str]]:
    codex_home = _get_codex_home()
    for candidate in ("auth.json", ".auth.json"):
        auth_path = codex_home / candidate
        if not auth_path.exists():
            continue
        raw, error = read_auth_json(auth_path)
        if error or raw is None:
            continue
        token, email, account_id = extract_auth_fields(raw)
        return (token or None), email, account_id
    return None, None, None


def _healthy_base_url_or_none(settings: Settings) -> Optional[str]:
    status_payload = service_status(settings)
    base_url = str(status_payload.get("base_url") or settings.base_url)
    healthy = bool(status_payload.get("healthy"))
    if not healthy:
        print(
            "Proxy is not healthy/running. Start with `cdx proxy` first.",
            file=sys.stderr,
        )
        return None
    return base_url


def _fetch_health_accounts(
    *, base_url: str, headers: Dict[str, str], timeout: float
) -> List[Dict[str, Any]]:
    payload = fetch_json(
        base_url=base_url,
        path="/health?refresh=1",
        headers=headers,
        timeout=timeout,
    )
    return _extract_accounts(payload)


def _next_auth_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    next_auth_file = str(payload.get("next_auth_file") or "").strip()
    next_auth_email = str(payload.get("next_auth_email") or "").strip()
    if not next_auth_file:
        return None

    for account in _extract_accounts(payload):
        auth_file = str(account.get("file") or "").strip()
        if auth_file != next_auth_file:
            continue
        selected = dict(account)
        if next_auth_email and not str(selected.get("email") or "").strip():
            selected["email"] = next_auth_email
        return selected

    selected: Dict[str, Any] = {"file": next_auth_file}
    if next_auth_email:
        selected["email"] = next_auth_email
    return selected


def _fetch_runtime_next_auth(
    *, base_url: str, headers: Dict[str, str], timeout: float
) -> Optional[Dict[str, Any]]:
    last_error: Exception | None = None
    for path in ("/health", "/trace?limit=1"):
        try:
            payload = fetch_json(
                base_url=base_url,
                path=path,
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            continue

        if path.startswith("/trace"):
            limits = payload.get("limits")
            if isinstance(limits, dict):
                next_auth = _next_auth_from_payload(limits)
                if next_auth is not None:
                    return next_auth
            continue

        next_auth = _next_auth_from_payload(payload)
        if next_auth is not None:
            return next_auth

    if last_error is not None:
        raise RuntimeError(str(last_error))
    return None
