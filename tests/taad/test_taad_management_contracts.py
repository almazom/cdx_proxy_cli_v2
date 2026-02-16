from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple
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
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, object]]:
    req = Request(f"{base_url}{path}", method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=2.0) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), json.loads(raw) if raw else {}


@contextmanager
def _running_proxy(*, auth_dir: str, management_key: str) -> Iterator[str]:
    settings = build_settings(
        auth_dir=auth_dir,
        host="127.0.0.1",
        port=0,
        upstream="http://127.0.0.1:9",
        management_key=management_key,
        trace_max=50,
    )
    runtime = ProxyRuntime(settings=settings)
    runtime.reload_auths()
    server = ProxyHTTPServer((settings.host, settings.port), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_taad_management_endpoints_require_management_key(tmp_path: Path) -> None:
    """TaaD Safety: management endpoints are protected from unauthorized access."""
    _write_auth(tmp_path / "primary.json", token="tok-1", email="a@example.com")

    with _running_proxy(auth_dir=str(tmp_path), management_key="mgmt-secret") as base_url:
        status, body = _request_json(base_url=base_url, path="/debug")
        assert status == 401
        assert body.get("error") == "unauthorized management request"

        status_ok, body_ok = _request_json(
            base_url=base_url,
            path="/debug",
            headers={"X-Management-Key": "mgmt-secret"},
        )
        assert status_ok == 200
        assert body_ok.get("status") == "running"
        assert body_ok.get("management_key_required") is True
        assert body_ok.get("auth_count") == 1


def test_taad_health_endpoint_is_operationally_readable(tmp_path: Path) -> None:
    """TaaD Operations: `/health` returns stable per-auth status structure."""
    _write_auth(tmp_path / "primary.json", token="tok-1", email="a@example.com")
    _write_auth(tmp_path / "backup.json", token="tok-2", email="b@example.com")

    with _running_proxy(auth_dir=str(tmp_path), management_key="mgmt-secret") as base_url:
        status, body = _request_json(
            base_url=base_url,
            path="/health?refresh=1",
            headers={"X-Management-Key": "mgmt-secret"},
        )
        assert status == 200
        assert isinstance(body.get("accounts"), list)
        accounts = body["accounts"]  # type: ignore[index]
        assert len(accounts) == 2
        first = accounts[0]
        assert "file" in first
        assert "status" in first
        assert "cooldown_seconds" in first
