"""Integration tests for codex CLI usage patterns.

Tests real-world scenarios:
- codex exec (POST /responses)
- codex trace (GET /trace)
- cdx all (management endpoints)
- Streaming responses
- WebSocket connections
- Concurrent requests
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.config.settings import Settings, build_settings
from cdx_proxy_cli_v2.proxy.server import (
    ProxyHTTPServer,
    ProxyRuntime,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_settings(tmp_path) -> Settings:
    """Create test settings with temp auth directory."""
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    return Settings(
        auth_dir=str(auth_dir),
        host="127.0.0.1",
        port=0,
        upstream="https://api.openai.com/v1",
        management_key="test-management-key-12345",
        allow_non_loopback=False,
        trace_max=100,
        request_timeout=45,
        compact_timeout=120,
    )


@pytest.fixture
def sample_auth_record() -> AuthRecord:
    """Create a sample auth record for testing."""
    return AuthRecord(
        name="test_auth.json",
        path="/tmp/test_auth.json",
        token="test-token-12345",
        email="test@example.com",
        account_id="acc-123",
    )


def _write_auth(path: Path, token: str, email: str, account_id: str = "") -> None:
    """Write an auth file."""
    data: Dict[str, object] = {"access_token": token, "email": email}
    if account_id:
        data["account_id"] = account_id
    path.write_text(json.dumps(data), encoding="utf-8")


def _request_json(
    *,
    base_url: str,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, object]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 3.0,
) -> Tuple[int, Dict[str, object]]:
    """Make a JSON request and return (status, body)."""
    req_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = Request(f"{base_url}{path}", data=data, method=method, headers=req_headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), json.loads(raw) if raw else {}


# ============================================================================
# Mock Upstream Server
# ============================================================================

class MockUpstreamHandler(BaseHTTPRequestHandler):
    """Mock upstream server that simulates OpenAI/ChatGPT API."""

    responses: List[Dict[str, object]] = []
    call_count: int = 0
    received_headers: List[Dict[str, str]] = []

    @classmethod
    def reset(cls):
        cls.responses = []
        cls.call_count = 0
        cls.received_headers = []

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: int, data: Dict[str, object]) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        MockUpstreamHandler.call_count += 1
        headers = {k: str(v) for k, v in self.headers.items()}
        MockUpstreamHandler.received_headers.append(headers)

        if self.path == "/v1/models":
            self._send_json(200, {"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]})
            return

        if "/responses" in self.path:
            # Simulate streaming response for codex exec
            if self.headers.get("Accept") == "text/event-stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                # Send a few SSE events
                events = [
                    b'data: {"type": "message_start"}\n\n',
                    b'data: {"type": "content_block_delta", "delta": {"text": "Hello"}}\n\n',
                    b'data: {"type": "content_block_delta", "delta": {"text": " World"}}\n\n',
                    b'data: {"type": "message_stop"}\n\n',
                ]
                for event in events:
                    self.wfile.write(event)
                    self.wfile.flush()
                return
            else:
                self._send_json(200, {"id": "resp_123", "status": "completed"})
                return

        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        MockUpstreamHandler.call_count += 1
        headers = {k: str(v) for k, v in self.headers.items()}
        MockUpstreamHandler.received_headers.append(headers)

        self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))

        # Check auth
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"error": {"code": "invalid_auth", "message": "Missing auth"}})
            return

        # Get response from queue or default
        if MockUpstreamHandler.responses:
            response = MockUpstreamHandler.responses.pop(0)
            status = int(response.get("status", 200))
            data = response.get("data", {})
            self._send_json(status, data)
            return

        # Default responses for common endpoints
        if "/responses" in self.path:
            # Simulate codex exec response
            if self.headers.get("Accept") == "text/event-stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                events = [
                    b'data: {"type": "response.created"}\n\n',
                    b'data: {"type": "response.output_item.added"}\n\n',
                    b'data: {"type": "done"}\n\n',
                ]
                for event in events:
                    self.wfile.write(event)
                    self.wfile.flush()
                return
            else:
                self._send_json(200, {
                    "id": "resp_123",
                    "object": "response",
                    "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "text", "text": "Hello!"}]}],
                })
                return

        if "/chat/completions" in self.path:
            self._send_json(200, {
                "id": "chatcmpl_123",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "Hello!"}}],
            })
            return

        self._send_json(404, {"error": "unknown endpoint"})


@pytest.fixture
def upstream_server() -> Iterator[Tuple[str, int]]:
    """Start a mock upstream server."""
    MockUpstreamHandler.reset()
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


@pytest.fixture
def proxy_server(test_settings, upstream_server) -> Iterator[Tuple[str, int, ProxyRuntime]]:
    """Start a proxy server with the mock upstream."""
    u_host, u_port = upstream_server
    settings = build_settings(
        auth_dir=test_settings.auth_dir,
        host="127.0.0.1",
        port=0,
        upstream=f"http://{u_host}:{u_port}",
        management_key="mgmt-secret",
        trace_max=100,
    )

    # Write auth files
    _write_auth(Path(settings.auth_dir) / "a.json", "tok-a", "a@example.com", "acc-a")
    _write_auth(Path(settings.auth_dir) / "b.json", "tok-b", "b@example.com", "acc-b")

    runtime = ProxyRuntime(settings=settings)
    runtime.reload_auths()

    server = ProxyHTTPServer((settings.host, settings.port), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address[:2]
        yield str(host), int(port), runtime
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


# ============================================================================
# Integration Tests: Codex CLI Patterns
# ============================================================================

class TestCodexExec:
    """Tests for 'codex exec' pattern - POST /responses."""

    def test_codex_exec_post_responses(self, proxy_server):
        """codex exec makes POST to /responses."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        status, body = _request_json(
            base_url=base_url,
            path="/v1/responses",
            method="POST",
            payload={"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]},
        )

        assert status == 200
        assert body.get("id") == "resp_123"
        assert body.get("status") == "completed"

    def test_codex_exec_with_streaming(self, proxy_server):
        """codex exec with streaming enabled."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        # Make request with Accept: text/event-stream
        req_headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        req = Request(
            f"{base_url}/v1/responses",
            data=json.dumps({"model": "gpt-4", "stream": True}).encode(),
            method="POST",
            headers=req_headers,
        )

        with urlopen(req, timeout=5.0) as resp:
            assert resp.status == 200
            assert resp.headers.get("Content-Type") == "text/event-stream"
            data = resp.read()
            assert b"data:" in data

    def test_codex_exec_auth_rotation_on_401(self, proxy_server):
        """codex exec should retry with next auth on 401."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        # Queue a 401 response for first auth
        MockUpstreamHandler.responses = [
            {"status": 401, "data": {"error": {"code": "invalid_token"}}},
            {"status": 200, "data": {"id": "resp_retry", "status": "completed"}},
        ]

        status, body = _request_json(
            base_url=base_url,
            path="/v1/responses",
            method="POST",
            payload={"model": "gpt-4"},
        )

        assert status == 200
        assert body.get("id") == "resp_retry"
        # Should have made 2 upstream calls (first 401, second 200)
        assert MockUpstreamHandler.call_count == 2

    def test_codex_exec_auth_rotation_on_account_incompatible_400(self, proxy_server):
        """codex exec should fail over when a key returns a known account-incompatible 400."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        MockUpstreamHandler.responses = [
            {
                "status": 400,
                "data": {
                    "detail": "The 'gpt-5.4' model is not supported when using Codex with a ChatGPT account."
                },
            },
            {"status": 200, "data": {"id": "resp_retry_400", "status": "completed"}},
        ]

        status, body = _request_json(
            base_url=base_url,
            path="/v1/responses",
            method="POST",
            payload={"model": "gpt-5.1-codex-max"},
        )

        assert status == 200
        assert body.get("id") == "resp_retry_400"
        assert MockUpstreamHandler.call_count == 2

    def test_codex_exec_eventually_fails_with_no_valid_auth(self, proxy_server):
        """codex exec should fail when all auths are invalid."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        # Queue 401 responses for all auths
        MockUpstreamHandler.responses = [
            {"status": 401, "data": {"error": {"code": "invalid_token"}}},
            {"status": 401, "data": {"error": {"code": "invalid_token"}}},
        ]

        status, body = _request_json(
            base_url=base_url,
            path="/v1/responses",
            method="POST",
            payload={"model": "gpt-4"},
        )

        # Should return 401 (last auth's status)
        assert status == 401
        # Should have tried both auths
        assert MockUpstreamHandler.call_count == 2


class TestCdxTrace:
    """Tests for 'cdx trace' pattern - GET /trace."""

    def test_cdx_trace_endpoint(self, proxy_server):
        """cdx trace should return request trace events."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        # First make a request to generate trace
        _request_json(
            base_url=base_url,
            path="/v1/responses",
            method="POST",
            payload={"model": "gpt-4"},
        )

        # Then query trace
        status, body = _request_json(
            base_url=base_url,
            path="/trace?limit=10",
            headers={"X-Management-Key": "mgmt-secret"},
        )

        assert status == 200
        events = body.get("events", [])
        assert isinstance(events, list)
        assert len(events) >= 1

    def test_cdx_trace_requires_management_key(self, proxy_server):
        """cdx trace should require management key."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        status, body = _request_json(
            base_url=base_url,
            path="/trace",
        )

        assert status == 401
        assert "unauthorized" in str(body.get("error", "")).lower()


class TestCdxAll:
    """Tests for 'cdx all' pattern - health and dashboard endpoints."""

    def test_cdx_all_health_endpoint(self, proxy_server):
        """cdx all uses /health to check auth status."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        status, body = _request_json(
            base_url=base_url,
            path="/health",
            headers={"X-Management-Key": "mgmt-secret"},
        )

        assert status == 200
        assert body.get("ok") is True
        accounts = body.get("accounts", [])
        assert len(accounts) == 2  # Two auth files

    def test_cdx_all_debug_endpoint(self, proxy_server):
        """cdx all uses /debug for proxy info."""
        host, port, runtime = proxy_server
        base_url = f"http://{host}:{port}"

        status, body = _request_json(
            base_url=base_url,
            path="/debug",
            headers={"X-Management-Key": "mgmt-secret"},
        )

        assert status == 200
        assert body.get("status") == "running"
        assert body.get("auth_count") == 2


class TestChatCompletions:
    """Tests for /v1/chat/completions endpoint."""

    def test_chat_completions_post(self, proxy_server):
        """POST /v1/chat/completions should work."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        status, body = _request_json(
            base_url=base_url,
            path="/v1/chat/completions",
            method="POST",
            payload={"model": "gpt-4", "messages": [{"role": "user", "content": "Hi"}]},
        )

        assert status == 200
        assert "choices" in body


class TestConcurrentRequests:
    """Tests for concurrent request handling."""

    def test_concurrent_codex_exec_requests(self, proxy_server):
        """Multiple concurrent codex exec requests should be handled."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"

        results: List[Tuple[int, Dict[str, object]]] = []
        errors: List[Exception] = []

        def make_request():
            try:
                result = _request_json(
                    base_url=base_url,
                    path="/v1/responses",
                    method="POST",
                    payload={"model": "gpt-4"},
                    timeout=10.0,
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Spawn 5 concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5
        for status, _body in results:
            assert status == 200


class TestAuthHeaderForwarding:
    """Tests that auth headers are correctly forwarded."""

    def test_bearer_token_forwarded(self, proxy_server):
        """Bearer token from auth file should be forwarded."""
        host, port, _runtime = proxy_server
        base_url = f"http://{host}:{port}"
        MockUpstreamHandler.reset()

        _request_json(
            base_url=base_url,
            path="/v1/responses",
            method="POST",
            payload={"model": "gpt-4"},
        )

        # Check that Authorization header was forwarded
        assert len(MockUpstreamHandler.received_headers) >= 1
        auth_header = MockUpstreamHandler.received_headers[0].get("Authorization", "")
        assert auth_header.startswith("Bearer ")
        # Should be one of our test tokens
        token = auth_header.replace("Bearer ", "")
        assert token in ["tok-a", "tok-b"]


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
