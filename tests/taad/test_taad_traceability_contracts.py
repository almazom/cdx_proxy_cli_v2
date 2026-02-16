from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cdx_proxy_cli_v2.config.settings import build_settings
from cdx_proxy_cli_v2.proxy.server import ProxyHTTPServer, ProxyRuntime


def _write_auth(path: Path, token: str, email: str) -> None:
    path.write_text(json.dumps({"access_token": token, "email": email}), encoding="utf-8")


def _request_json(
    *,
    base_url: str,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, object]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, object]]:
    req_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = Request(f"{base_url}{path}", data=data, method=method, headers=req_headers)
    try:
        with urlopen(req, timeout=3.0) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), json.loads(raw) if raw else {}


@dataclass
class UpstreamProbe:
    auth_headers: List[str] = field(default_factory=list)
    call_count: int = 0


def _build_upstream_handler(state: UpstreamProbe) -> type[BaseHTTPRequestHandler]:
    class UpstreamHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            state.call_count += 1
            state.auth_headers.append(str(self.headers.get("Authorization") or ""))
            body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
            _ = body

            if state.call_count == 1:
                payload = {"error": "auth expired"}
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return

            payload = {"ok": True}
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return UpstreamHandler


@contextmanager
def _running_http_server(server: ThreadingHTTPServer) -> Iterator[Tuple[str, int]]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_taad_retry_flow_is_traceable_with_single_request_id(tmp_path: Path) -> None:
    """TaaD Traceability: retries must preserve `request_id` and increment `attempt`."""
    _write_auth(tmp_path / "a.json", token="tok-a", email="a@example.com")
    _write_auth(tmp_path / "b.json", token="tok-b", email="b@example.com")

    upstream_probe = UpstreamProbe()
    upstream_server = ThreadingHTTPServer(("127.0.0.1", 0), _build_upstream_handler(upstream_probe))
    with _running_http_server(upstream_server) as (_u_host, u_port):
        settings = build_settings(
            auth_dir=str(tmp_path),
            host="127.0.0.1",
            port=0,
            upstream=f"http://127.0.0.1:{u_port}",
            management_key="mgmt-secret",
            trace_max=100,
        )
        runtime = ProxyRuntime(settings=settings)
        runtime.reload_auths()
        proxy_server = ProxyHTTPServer((settings.host, settings.port), runtime)
        with _running_http_server(proxy_server) as (p_host, p_port):
            proxy_base_url = f"http://{p_host}:{p_port}"

            status, body = _request_json(
                base_url=proxy_base_url,
                path="/responses",
                method="POST",
                payload={"ping": "taad"},
            )
            assert status == 200
            assert body.get("ok") is True

            trace_status, trace_body = _request_json(
                base_url=proxy_base_url,
                path="/trace?limit=10",
                headers={"X-Management-Key": "mgmt-secret"},
            )
            assert trace_status == 200
            events = trace_body.get("events")
            assert isinstance(events, list)

            request_events = [item for item in events if isinstance(item, dict) and item.get("path") == "/responses"]
            assert len(request_events) == 2
            first, second = request_events[0], request_events[1]

            assert first.get("attempt") == 1
            assert second.get("attempt") == 2
            assert first.get("status") == 401
            assert second.get("status") == 200
            assert first.get("request_id") == second.get("request_id")
            assert first.get("auth_file") != second.get("auth_file")

    assert upstream_probe.call_count == 2
    assert upstream_probe.auth_headers[0] == "Bearer tok-a"
    assert upstream_probe.auth_headers[1] == "Bearer tok-b"
