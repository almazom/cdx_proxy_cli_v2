"""Tests for WebSocket HTTP version handling and auth error scenarios.

This module addresses two specific error conditions:
1. WebSocket protocol error: HTTP version must be 1.1 or higher
2. 503 Service Unavailable: "no auths available"
"""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import DEFAULT_BLACKLIST_SECONDS
from cdx_proxy_cli_v2.config.settings import Settings
from cdx_proxy_cli_v2.proxy.server import (
    ProxyHandler,
    ProxyRuntime,
    UpstreamAttemptResult,
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


def _build_runtime(settings: Settings, auth_records: list[AuthRecord]) -> ProxyRuntime:
    """Create a proxy runtime seeded with auth records."""
    runtime = ProxyRuntime(settings=settings)
    runtime.auth_pool.load(auth_records)
    # For backwards compatibility in tests: blacklist on first error
    runtime.auth_pool.consecutive_error_threshold = 1
    return runtime


def _build_proxy_handler(
    *,
    runtime: ProxyRuntime,
    path: str,
    headers: Dict[str, str],
    body: bytes = b"",
    method: str = "POST",
) -> ProxyHandler:
    """Create a proxy handler instance with mocked network I/O."""
    handler = ProxyHandler.__new__(ProxyHandler)
    handler.server = MagicMock()
    handler.server.runtime = runtime
    handler.path = path
    handler.command = method
    handler.headers = headers
    handler.client_address = ("127.0.0.1", 43123)
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler._read_body = MagicMock(return_value=body)
    return handler


# ============================================================================
# Test: HTTP Version Handling for WebSocket Compatibility
# ============================================================================


class TestHTTPVersionHandling:
    """Tests for HTTP/1.1 version enforcement for WebSocket compatibility."""

    def test_http_connection_uses_http11(self, test_settings, sample_auth_record):
        """HTTPConnection should be configured for HTTP/1.1."""
        runtime = _build_runtime(test_settings, [sample_auth_record])
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={
                "Authorization": "Bearer test",
                "Content-Type": "application/json",
            },
            body=b'{"model": "gpt-4"}',
        )

        mock_connection = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.getheaders.return_value = [("Content-Type", "application/json")]
        mock_response.getheader.return_value = "application/json"
        mock_response.read.return_value = b'{"id": "test"}'
        mock_connection.getresponse.return_value = mock_response

        captured_attrs = {}

        def capture_http_attrs(*args, **kwargs):
            captured_attrs["http_vsn"] = getattr(mock_connection, "_http_vsn", None)
            captured_attrs["http_vsn_str"] = getattr(
                mock_connection, "_http_vsn_str", None
            )
            return None

        mock_connection.request = MagicMock(side_effect=capture_http_attrs)

        with patch("http.client.HTTPSConnection", return_value=mock_connection):
            result = handler._run_upstream_attempt(
                scheme="https",
                host="api.openai.com",
                port=443,
                rewritten_path="/v1/chat/completions",
                full_path="/v1/chat/completions",
                body=b'{"model": "gpt-4"}',
                headers={"Authorization": "Bearer test"},
                request_timeout=45,
                compact_timeout=120,
            )

        # Verify HTTP version was set to 1.1
        assert mock_connection._http_vsn == 11, (
            f"Expected _http_vsn=11, got {mock_connection._http_vsn}"
        )
        assert mock_connection._http_vsn_str == "HTTP/1.1", (
            f"Expected _http_vsn_str='HTTP/1.1', got {mock_connection._http_vsn_str}"
        )
        assert result.status == 200

    def test_http_connection_uses_http11_for_http_scheme(
        self, test_settings, sample_auth_record
    ):
        """HTTPConnection should use HTTP/1.1 even for non-TLS connections."""
        runtime = _build_runtime(test_settings, [sample_auth_record])
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={
                "Authorization": "Bearer test",
                "Content-Type": "application/json",
            },
            body=b'{"model": "gpt-4"}',
        )

        mock_connection = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.getheaders.return_value = [("Content-Type", "application/json")]
        mock_response.getheader.return_value = "application/json"
        mock_response.read.return_value = b'{"id": "test"}'
        mock_connection.getresponse.return_value = mock_response

        with patch("http.client.HTTPConnection", return_value=mock_connection):
            result = handler._run_upstream_attempt(
                scheme="http",
                host="localhost",
                port=8080,
                rewritten_path="/v1/chat/completions",
                full_path="/v1/chat/completions",
                body=b'{"model": "gpt-4"}',
                headers={"Authorization": "Bearer test"},
                request_timeout=45,
                compact_timeout=120,
            )

        # Verify HTTP version was set to 1.1
        assert mock_connection._http_vsn == 11
        assert mock_connection._http_vsn_str == "HTTP/1.1"
        assert result.status == 200

    def test_websocket_upgrade_request_uses_http11(
        self, test_settings, sample_auth_record
    ):
        """WebSocket upgrade requests must use HTTP/1.1."""
        runtime = _build_runtime(test_settings, [sample_auth_record])
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={
                "Authorization": "Bearer test",
                "Content-Type": "application/json",
                "Upgrade": "websocket",
                "Connection": "Upgrade",
            },
            body=b'{"model": "gpt-4", "stream": true}',
        )

        mock_connection = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 101  # Switching Protocols
        mock_response.getheaders.return_value = [
            ("Upgrade", "websocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Accept", "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="),
        ]
        mock_response.getheader.side_effect = lambda name, default=None: {
            "Upgrade": "websocket",
            "Connection": "Upgrade",
        }.get(name, default)
        mock_connection.getresponse.return_value = mock_response

        with patch("http.client.HTTPSConnection", return_value=mock_connection):
            result = handler._run_upstream_attempt(
                scheme="https",
                host="api.openai.com",
                port=443,
                rewritten_path="/v1/responses",
                full_path="/v1/responses",
                body=b'{"model": "gpt-4", "stream": true}',
                headers={"Authorization": "Bearer test"},
                request_timeout=45,
                compact_timeout=120,
            )

        # Verify HTTP version was set to 1.1 for WebSocket upgrade
        assert mock_connection._http_vsn == 11
        assert mock_connection._http_vsn_str == "HTTP/1.1"
        assert result.websocket_upgrade is True
        assert result.stream_connection is mock_connection
        assert result.stream_response is mock_response


# ============================================================================
# Test: "No Auths Available" Error Scenarios
# ============================================================================


class TestNoAuthsAvailableError:
    """Tests for 503 'no auths available' error conditions."""

    def test_returns_503_when_no_auths_loaded(self, test_settings):
        """Should return 503 when auth pool is empty."""
        runtime = _build_runtime(test_settings, [])  # No auths
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )

        handler._proxy_request()

        # Should send 503 response
        handler.send_response.assert_called_once()
        call_args = handler.send_response.call_args
        assert call_args[0][0] == 503, f"Expected 503, got {call_args[0][0]}"

    def test_returns_503_when_all_auths_blacklisted(
        self, test_settings, sample_auth_record
    ):
        """Should return 503 when all auth keys are blacklisted."""
        runtime = _build_runtime(test_settings, [sample_auth_record])
        # Mark the auth as blacklisted (401/403 triggers blacklist)
        runtime.auth_pool.mark_result(
            sample_auth_record.name, status=401, error_code="token_invalid"
        )

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )

        handler._proxy_request()

        # Should send 503 response
        call_args = handler.send_response.call_args
        assert call_args[0][0] == 503, f"Expected 503, got {call_args[0][0]}"

    def test_returns_503_when_all_auths_in_cooldown(
        self, test_settings, sample_auth_record
    ):
        """Should return 503 when all auth keys are in cooldown."""
        runtime = _build_runtime(test_settings, [sample_auth_record])
        # Mark the auth as rate limited (429 triggers cooldown)
        runtime.auth_pool.mark_result(sample_auth_record.name, status=429)

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )

        handler._proxy_request()

        # Should send 503 response
        call_args = handler.send_response.call_args
        assert call_args[0][0] == 503, f"Expected 503, got {call_args[0][0]}"

    def test_error_body_contains_no_auths_message(self, test_settings):
        """503 response body should contain 'no auths available' message."""
        runtime = _build_runtime(test_settings, [])  # No auths
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )

        written_data = []

        def capture_write(data):
            written_data.append(data)

        handler.wfile.write = capture_write

        handler._proxy_request()

        # Check that response body contains expected error message
        found_error_message = False
        for data in written_data:
            if b"no auths available" in data:
                found_error_message = True
                break
        assert found_error_message, "Expected 'no auths available' in response body"

    def test_retries_on_401_and_cycles_to_next_auth(self, test_settings):
        """Should retry with next auth on 401 response."""
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        runtime = _build_runtime(test_settings, [auth1, auth2])

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )

        call_count = 0
        captured_tokens = []

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            nonlocal call_count
            call_count += 1
            headers = kwargs.get("headers", {})
            auth_header = headers.get("Authorization", "")
            captured_tokens.append(auth_header)

            # First auth returns 401, second returns 200
            if call_count == 1:
                return UpstreamAttemptResult(
                    status=401,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"error": {"code": "invalid_token"}}',
                    error_code="invalid_token",
                )
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"id": "success"}',
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)
        handler._proxy_request()

        # Should have tried both auths
        assert call_count == 2
        assert handler.send_response.call_args[0][0] == 200

    def test_retries_on_account_incompatible_400_and_cycles_to_next_auth(
        self, test_settings
    ):
        """Known account-incompatible 400s should blacklist the key and retry the next auth."""
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            [auth1, auth2],
        )

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-5.1-codex-max"}',
        )

        call_count = 0
        captured_tokens = []

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            nonlocal call_count
            call_count += 1
            headers = kwargs.get("headers", {})
            captured_tokens.append(headers.get("Authorization", ""))

            if call_count == 1:
                return UpstreamAttemptResult(
                    status=400,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"detail": "The \'gpt-5.4\' model is not supported when using Codex with a ChatGPT account."}',
                    error_code="chatgpt_account_incompatible",
                )
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"id": "success"}',
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)
        handler._proxy_request()

        assert call_count == 2
        assert captured_tokens == ["Bearer token1", "Bearer token2"]
        assert handler.send_response.call_args[0][0] == 200
        assert runtime.auth_pool.stats()["blacklist"] == 1

    def test_cycles_through_all_auths_before_503(self, test_settings):
        """Should try all available auths before returning 503."""
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        auth3 = AuthRecord(
            name="auth3.json",
            path="/tmp/auth3.json",
            token="token3",
            email="c@example.com",
        )
        runtime = _build_runtime(test_settings, [auth1, auth2, auth3])

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )

        call_count = 0

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            nonlocal call_count
            call_count += 1
            # All auths return 401
            return UpstreamAttemptResult(
                status=401,
                headers=[("Content-Type", "application/json")],
                body=b'{"error": {"code": "invalid_token"}}',
                error_code="invalid_token",
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)
        handler._proxy_request()

        # Should have tried all 3 auths
        assert call_count == 3
        # Final status should be 401 (last auth's status)
        assert handler.send_response.call_args[0][0] == 401

    def test_websocket_transport_failures_do_not_rotate_or_blacklist_auths(
        self, test_settings
    ):
        """Optional websocket transport probes should not cycle through or penalize auths."""
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            [auth1, auth2],
        )

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/responses",
            method="GET",
            headers={
                "Accept": "*/*",
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "test-key",
                "Sec-WebSocket-Version": "13",
            },
        )

        call_count = 0

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            nonlocal call_count
            call_count += 1
            return UpstreamAttemptResult(
                status=405,
                headers=[("Content-Type", "application/json")],
                body=b'{"detail":"Method Not Allowed"}',
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)
        handler._proxy_request()

        assert call_count == 1
        assert handler.send_response.call_args[0][0] == 405
        assert runtime.auth_pool.stats()["ok"] == 2

    def test_websocket_auth_failures_rotate_to_next_auth(self, test_settings):
        """Websocket auth failures should mark the key unhealthy and retry with the next auth."""
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            [auth1, auth2],
        )
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/responses",
            method="GET",
            headers={
                "Accept": "*/*",
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "test-key",
                "Sec-WebSocket-Version": "13",
            },
        )
        handler._tunnel_websocket = MagicMock()

        stream_connection = MagicMock()
        stream_connection.sock = MagicMock()
        stream_response = MagicMock()
        call_count = 0

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return UpstreamAttemptResult(
                    status=401,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"error":{"code":"token_invalid"}}',
                    error_code="token_invalid",
                )
            return UpstreamAttemptResult(
                status=101,
                headers=[
                    ("Upgrade", "websocket"),
                    ("Connection", "Upgrade"),
                    ("Sec-WebSocket-Accept", "abc"),
                ],
                body=b"",
                stream_connection=stream_connection,
                stream_response=stream_response,
                websocket_upgrade=True,
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)

        handler._proxy_request()

        stats = runtime.auth_pool.stats()
        assert call_count == 2
        assert handler.send_response.call_args[0][0] == 101
        assert stats["blacklist"] == 1
        assert stats["ok"] == 1
        handler._tunnel_websocket.assert_called_once_with(
            upstream_connection=stream_connection,
            upstream_response=stream_response,
        )

    def test_websocket_upgrade_101_triggers_tunnel(
        self, test_settings, sample_auth_record
    ):
        """Successful websocket upgrades should switch into tunnel mode."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            [sample_auth_record],
        )
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/responses",
            method="GET",
            headers={
                "Accept": "*/*",
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "test-key",
                "Sec-WebSocket-Version": "13",
            },
        )
        handler._tunnel_websocket = MagicMock()

        stream_connection = MagicMock()
        stream_connection.sock = MagicMock()
        stream_response = MagicMock()

        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=101,
                headers=[
                    ("Upgrade", "websocket"),
                    ("Connection", "Upgrade"),
                    ("Sec-WebSocket-Accept", "abc"),
                ],
                body=b"",
                stream_connection=stream_connection,
                stream_response=stream_response,
                websocket_upgrade=True,
            )
        )

        handler._proxy_request()

        assert handler.send_response.call_args[0][0] == 101
        handler._tunnel_websocket.assert_called_once_with(
            upstream_connection=stream_connection,
            upstream_response=stream_response,
        )


# ============================================================================
# Test: Auth Pool Exhaustion Edge Cases
# ============================================================================


class TestAuthPoolExhaustion:
    """Tests for auth pool exhaustion scenarios."""

    def test_mixed_available_and_unavailable_auths(self, test_settings):
        """Should use available auth when others are unavailable."""
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        runtime = _build_runtime(test_settings, [auth1, auth2])

        # Mark auth1 as blacklisted
        runtime.auth_pool.mark_result(
            auth1.name, status=401, error_code="token_invalid"
        )

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )

        captured_tokens = []

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            headers = kwargs.get("headers", {})
            auth_header = headers.get("Authorization", "")
            captured_tokens.append(auth_header)
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"id": "success"}',
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)
        handler._proxy_request()

        # Should have used auth2 (the available one)
        assert len(captured_tokens) == 1
        assert "token2" in captured_tokens[0]
        assert handler.send_response.call_args[0][0] == 200


class TestSingleKeyAutoReset:
    """Tests for opt-in one-key starvation recovery."""

    def test_resets_blacklist_and_probation_after_single_key_streak(
        self, test_settings, monkeypatch
    ):
        now = 1000.0
        monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
        monkeypatch.setattr("cdx_proxy_cli_v2.proxy.server.time.time", lambda: now)

        settings = replace(
            test_settings,
            auto_reset_on_single_key=True,
            auto_reset_streak=3,
            auto_reset_cooldown=120,
        )
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        auth3 = AuthRecord(
            name="auth3.json",
            path="/tmp/auth3.json",
            token="token3",
            email="c@example.com",
        )
        runtime = _build_runtime(settings, [auth1, auth2, auth3])

        runtime.auth_pool.mark_result(
            auth2.name, status=401, error_code="token_invalid"
        )
        now += float(DEFAULT_BLACKLIST_SECONDS) + 1.0
        runtime.auth_pool.mark_result(
            auth3.name, status=401, error_code="token_invalid"
        )

        for attempt in range(1, 4):
            runtime.record_attempt(
                request_id=f"req-{attempt}",
                method="POST",
                path="/v1/chat/completions",
                route="request",
                status=200,
                latency_ms=25,
                auth_name=auth1.name,
                auth_email=auth1.email,
                attempt=attempt,
                client_ip="127.0.0.1",
            )
            runtime.auth_pool.mark_result(auth1.name, status=200)

        reset_count = runtime.maybe_auto_reset_single_key_stall()

        assert reset_count == 2
        accounts = {
            item["file"]: item for item in runtime.health_snapshot()["accounts"]
        }
        assert accounts[auth1.name]["status"] == "OK"
        assert accounts[auth2.name]["status"] == "OK"
        assert accounts[auth3.name]["status"] == "OK"

    def test_does_not_reset_cooldown_only_keys(self, test_settings, monkeypatch):
        now = 2000.0
        monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
        monkeypatch.setattr("cdx_proxy_cli_v2.proxy.server.time.time", lambda: now)

        settings = replace(
            test_settings,
            auto_reset_on_single_key=True,
            auto_reset_streak=2,
            auto_reset_cooldown=120,
        )
        auth1 = AuthRecord(
            name="auth1.json",
            path="/tmp/auth1.json",
            token="token1",
            email="a@example.com",
        )
        auth2 = AuthRecord(
            name="auth2.json",
            path="/tmp/auth2.json",
            token="token2",
            email="b@example.com",
        )
        runtime = _build_runtime(settings, [auth1, auth2])

        runtime.auth_pool.mark_result(auth2.name, status=429)
        for attempt in range(1, 3):
            runtime.record_attempt(
                request_id=f"cooldown-{attempt}",
                method="POST",
                path="/v1/chat/completions",
                route="request",
                status=200,
                latency_ms=10,
                auth_name=auth1.name,
                auth_email=auth1.email,
                attempt=attempt,
                client_ip="127.0.0.1",
            )
            runtime.auth_pool.mark_result(auth1.name, status=200)

        reset_count = runtime.maybe_auto_reset_single_key_stall()

        assert reset_count == 0
        accounts = {
            item["file"]: item for item in runtime.health_snapshot()["accounts"]
        }
        assert accounts[auth2.name]["status"] == "COOLDOWN"

    def test_proxy_request_calls_auto_reset_hook(
        self, test_settings, sample_auth_record
    ):
        settings = replace(
            test_settings,
            auto_reset_on_single_key=True,
            auto_reset_streak=2,
            auto_reset_cooldown=120,
        )
        runtime = _build_runtime(settings, [sample_auth_record])
        runtime.maybe_auto_reset_single_key_stall = MagicMock(return_value=0)

        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b'{"model": "gpt-4"}',
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"id":"ok"}',
            )
        )

        handler._proxy_request()

        runtime.maybe_auto_reset_single_key_stall.assert_called_once()
        assert handler.send_response.call_args[0][0] == 200


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
