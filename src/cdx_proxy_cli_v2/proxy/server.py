from __future__ import annotations

import argparse
import hmac
import http.client
import json
import os
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from cdx_proxy_cli_v2.auth.store import load_auth_records
from cdx_proxy_cli_v2.observability.event_log import EventLogger
from cdx_proxy_cli_v2.proxy.rules import (
    CHATGPT_HOSTS,
    build_forward_headers,
    is_loopback_host,
    is_primary_responses_path,
    management_route,
    rewrite_request_path,
    set_header_case_insensitive,
    trace_route,
)
from cdx_proxy_cli_v2.auth.rotation import RoundRobinAuthPool
from cdx_proxy_cli_v2.config.settings import Settings, build_settings
from cdx_proxy_cli_v2.observability.trace_store import TraceStore

DEFAULT_MAX_REQUEST_BODY = 10 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BODY = 10 * 1024 * 1024


def _extract_error_code(raw_body: bytes) -> Optional[str]:
    if not raw_body:
        return None
    try:
        parsed = json.loads(raw_body.decode("utf-8", errors="replace"))
    except Exception:
        return None
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip()
        code = parsed.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return None


@dataclass
class ProxyRuntime:
    settings: Settings
    auth_pool: RoundRobinAuthPool = field(default_factory=RoundRobinAuthPool)
    trace_store: TraceStore = field(init=False)
    logger: EventLogger = field(init=False)

    def __post_init__(self) -> None:
        self.trace_store = TraceStore(max_size=self.settings.trace_max)
        self.logger = EventLogger(self.settings.auth_dir)

    def reload_auths(self) -> int:
        records = load_auth_records(self.settings.auth_dir)
        self.auth_pool.load(records)
        return len(records)

    def health_snapshot(self, *, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            self.reload_auths()
        accounts = self.auth_pool.health_snapshot()
        return {
            "ok": bool(accounts),
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
            "pid": os.getpid(),
            "event_log_file": str(self.logger.path),
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
        self.logger.write(
            level="INFO" if status < 500 else "WARN",
            event="proxy.request",
            message="request attempt completed",
            **payload,
        )


class ProxyHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: Tuple[str, int], runtime: ProxyRuntime):
        super().__init__(server_address, ProxyHandler)
        self.runtime = runtime

    def initiate_shutdown(self) -> None:
        threading.Thread(target=self.shutdown, daemon=True).start()


class ProxyHandler(BaseHTTPRequestHandler):
    server: ProxyHTTPServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

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
        self.wfile.write(raw)

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

    def _handle_management(self, route: str) -> None:
        host, port = self.server.server_address[:2]
        runtime = self.server.runtime
        if route == "debug":
            self._send_json(200, runtime.debug_payload(host=str(host), port=int(port)))
            return
        if route == "trace":
            limit = 0
            query = urlsplit(self.path).query
            if query:
                params = parse_qs(query)
                if params.get("limit"):
                    try:
                        limit = int(params["limit"][0])
                    except (ValueError, TypeError):
                        limit = 0
            self._send_json(200, {"events": runtime.trace_events(limit=limit)})
            return
        if route == "health":
            refresh = False
            query = urlsplit(self.path).query
            if query:
                params = parse_qs(query)
                refresh = params.get("refresh", ["0"])[0] == "1"
            self._send_json(200, runtime.health_snapshot(refresh=refresh))
            return
        if route == "auth-files":
            self._send_json(200, {"files": runtime.auth_pool.auth_files()})
            return
        if route == "shutdown":
            self._send_json(200, {"status": "shutting_down"})
            runtime.logger.write(level="INFO", event="proxy.shutdown_requested", message="shutdown requested")
            self.server.initiate_shutdown()
            return
        self._send_json(404, {"error": "unknown management route"})

    def _proxy_request(self) -> None:
        runtime = self.server.runtime
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
            full_path = f"{base_path}{rewritten_path}" if base_path else rewritten_path

        chatgpt_backend = host.lower() in CHATGPT_HOSTS and base_path.rstrip("/") == "/backend-api"
        chatgpt_responses_mode = bool(chatgpt_backend and is_primary_responses_path(rewritten_path))

        body = self._read_body()
        if body is None:
            return

        base_headers = build_forward_headers(
            dict(self.headers),
            chatgpt_responses_mode=chatgpt_responses_mode,
        )
        if body and not any(key.lower() == "content-type" for key in base_headers.keys()):
            set_header_case_insensitive(base_headers, "Content-Type", self.headers.get("Content-Type", "application/json"))
        if chatgpt_backend:
            base_headers.setdefault("Origin", "https://chatgpt.com")
            base_headers.setdefault("Referer", "https://chatgpt.com/")
            base_headers.setdefault("User-Agent", "codex-cli")

        max_attempts = max(1, runtime.auth_pool.count())
        request_id = uuid.uuid4().hex[:12]
        client_ip = self.client_address[0] if self.client_address else None

        final_status = 503
        final_headers: List[Tuple[str, str]] = [("Content-Type", "application/json")]
        final_body = json.dumps({"error": "no auths available"}).encode("utf-8")
        stream_response: Optional[http.client.HTTPResponse] = None
        stream_connection: Optional[http.client.HTTPConnection] = None

        attempt = 0
        while attempt < max_attempts:
            auth_state = runtime.auth_pool.pick()
            if not auth_state:
                break

            headers = dict(base_headers)
            set_header_case_insensitive(headers, "Authorization", f"Bearer {auth_state.record.token}")
            if chatgpt_backend and auth_state.record.account_id:
                set_header_case_insensitive(headers, "chatgpt-account-id", str(auth_state.record.account_id))

            error_message: Optional[str] = None
            error_code: Optional[str] = None
            start = time.time()
            connection: Optional[http.client.HTTPConnection] = None
            try:
                conn_cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
                connection = conn_cls(host, port, timeout=25)
                connection.request(self.command, full_path, body=body, headers=headers)
                response = connection.getresponse()
                final_status = response.status
                final_headers = response.getheaders()
                content_type = str(response.getheader("Content-Type") or "")
                if "text/event-stream" in content_type.lower():
                    stream_response = response
                    stream_connection = connection
                    connection = None
                    final_body = b""
                else:
                    data = response.read(DEFAULT_MAX_RESPONSE_BODY + 1)
                    if len(data) > DEFAULT_MAX_RESPONSE_BODY:
                        final_status = 413
                        final_headers = [("Content-Type", "application/json")]
                        final_body = json.dumps({"error": "response body too large"}).encode("utf-8")
                    else:
                        final_body = data
                        error_code = _extract_error_code(final_body)
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
                final_status = 502
                final_headers = [("Content-Type", "application/json")]
                final_body = json.dumps(
                    {"error": "upstream request failed", "detail": error_message}
                ).encode("utf-8")
                error_code = "upstream_request_failed"
            finally:
                latency_ms = int((time.time() - start) * 1000)
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
                    error=error_message,
                )
                runtime.auth_pool.mark_result(
                    auth_state.record.name,
                    status=final_status,
                    error_code=error_code,
                )
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass

            if final_status in {401, 403, 429}:
                attempt += 1
                if attempt < max_attempts:
                    continue
            break

        self.send_response(final_status)
        for key, value in final_headers:
            normalized = key.lower()
            if normalized in {"transfer-encoding", "connection", "content-length"}:
                continue
            self.send_header(key, value)

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

        self.send_header("Content-Length", str(len(final_body)))
        self.end_headers()
        if final_body:
            self.wfile.write(final_body)


def run_proxy_server(settings: Settings) -> None:
    if not is_loopback_host(settings.host) and not settings.allow_non_loopback:
        raise ValueError("non-loopback bind blocked; use --allow-non-loopback to override")
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
    )
    run_proxy_server(settings)
    return 0
