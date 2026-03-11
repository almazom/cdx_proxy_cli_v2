from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import pytest

from cdx_proxy_cli_v2.config.settings import Settings, build_settings
from cdx_proxy_cli_v2.proxy.server import ProxyHTTPServer, ProxyRuntime

from tests.integration.support import MockUpstreamHandler, write_auth

MANAGEMENT_KEY = "mgmt-secret"


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    return Settings(
        auth_dir=str(auth_dir),
        host="127.0.0.1",
        port=0,
        upstream="https://api.openai.com/v1",
        management_key=MANAGEMENT_KEY,
        allow_non_loopback=False,
        trace_max=100,
        request_timeout=45,
        compact_timeout=120,
    )


@pytest.fixture
def auth_dir(test_settings: Settings) -> Path:
    return Path(test_settings.auth_dir)


@pytest.fixture
def upstream_server() -> Iterator[str]:
    MockUpstreamHandler.reset()
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


@pytest.fixture
def proxy_server(
    test_settings: Settings,
    auth_dir: Path,
    upstream_server: str,
) -> Iterator[dict[str, Any]]:
    settings = build_settings(
        auth_dir=test_settings.auth_dir,
        host="127.0.0.1",
        port=0,
        upstream=upstream_server,
        management_key=MANAGEMENT_KEY,
        trace_max=100,
    )

    write_auth(auth_dir / "a.json", "tok-a", "a@example.com", "acc-a")
    write_auth(auth_dir / "b.json", "tok-b", "b@example.com", "acc-b")

    runtime = ProxyRuntime(settings=settings)
    runtime.reload_auths()

    server = ProxyHTTPServer((settings.host, settings.port), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address[:2]
        yield {
            "base_url": f"http://{host}:{port}",
            "management_key": MANAGEMENT_KEY,
            "runtime": runtime,
        }
    finally:
        server.shutdown()
        server.server_close()
        runtime.shutdown()
        thread.join(timeout=2.0)
