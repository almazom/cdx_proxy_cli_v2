"""Comprehensive tests for proxy server module."""

from __future__ import annotations

from dataclasses import replace
import json
from io import BytesIO
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import RoundRobinAuthPool
from cdx_proxy_cli_v2.config.settings import Settings
from cdx_proxy_cli_v2.proxy.server import (
    ProxyHandler,
    ProxyRuntime,
    UpstreamAttemptResult,
    _extract_error_code,
    _normalize_models_response_body,
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
        upstream="https://api.example.com/v1",
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


@pytest.fixture
def mock_auth_pool(sample_auth_record) -> RoundRobinAuthPool:
    """Create a mock auth pool with a sample record."""
    pool = RoundRobinAuthPool(
        consecutive_error_threshold=1
    )  # Blacklist on first error for test
    pool.load([sample_auth_record])
    return pool


def _build_runtime(settings: Settings, auth_record: AuthRecord) -> ProxyRuntime:
    """Create a proxy runtime seeded with a single auth record."""
    runtime = ProxyRuntime(settings=settings)
    runtime.auth_pool.load([auth_record])
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
# Test: _extract_error_code
# ============================================================================


class TestExtractErrorCode:
    """Tests for _extract_error_code helper function."""

    def test_returns_none_for_empty_body(self):
        """Empty body should return None."""
        assert _extract_error_code(b"") is None

    def test_returns_none_for_invalid_json(self):
        """Invalid JSON should return None."""
        assert _extract_error_code(b"not json") is None

    def test_extracts_error_code_from_error_object(self):
        """Should extract code from error object."""
        body = json.dumps({"error": {"code": "invalid_token"}}).encode()
        assert _extract_error_code(body) == "invalid_token"

    def test_extracts_code_from_top_level(self):
        """Should extract code from top-level if no error object."""
        body = json.dumps({"code": "rate_limited"}).encode()
        assert _extract_error_code(body) == "rate_limited"

    def test_returns_none_for_missing_code(self):
        """Should return None if code is missing."""
        body = json.dumps({"error": {"message": "Something went wrong"}}).encode()
        assert _extract_error_code(body) is None

    def test_handles_whitespace_in_code(self):
        """Should strip whitespace from code."""
        body = json.dumps({"error": {"code": "  spaced_code  "}}).encode()
        assert _extract_error_code(body) == "spaced_code"

    def test_handles_non_string_code(self):
        """Should return None for non-string code."""
        body = json.dumps({"error": {"code": 12345}}).encode()
        assert _extract_error_code(body) is None

    def test_classifies_chatgpt_account_incompatibility_from_detail(self):
        """Known ChatGPT-account incompatibility details should map to a hard auth error code."""
        body = json.dumps(
            {
                "detail": "The 'gpt-5.4' model is not supported when using Codex with a ChatGPT account."
            }
        ).encode()
        assert _extract_error_code(body, status=400) == "chatgpt_account_incompatible"


# ============================================================================
# Test: Management Route Detection
# ============================================================================


class TestManagementRouteDetection:
    """Tests for management route detection."""

    def test_management_route_debug(self):
        """Debug endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route("/debug") == "debug"

    def test_management_route_trace(self):
        """Trace endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route("/trace") == "trace"

    def test_management_route_health(self):
        """Health endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route("/health") == "health"

    def test_management_route_auth_files(self):
        """Auth-files endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route("/auth-files") == "auth-files"

    def test_management_route_shutdown(self):
        """Shutdown endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route("/shutdown") == "shutdown"

    def test_non_management_route_returns_none(self):
        """Non-management paths should return None."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route("/v1/chat/completions") is None
        assert management_route("/api/models") is None
        assert management_route("/some/random/path") is None


# ============================================================================
# Test: Trace Route Classification
# ============================================================================


class TestTraceRouteClassification:
    """Tests for trace route classification."""

    def test_trace_route_request(self):
        """/responses path should be classified as 'request'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route

        assert trace_route("/responses") == "responses"
        assert trace_route("/codex/responses") == "responses"

    def test_trace_route_compact(self):
        """Paths ending in /compact should be classified as 'compact'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route

        assert trace_route("/responses/compact") == "compact"
        assert trace_route("/responses/compact?x=1") == "compact"

    def test_trace_route_other(self):
        """Other paths should be classified as 'other'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route

        assert trace_route("/health") == "management"
        assert trace_route("/debug") == "management"
        assert trace_route("/v1/models") == "models"
        assert trace_route("/totally/unknown") == ""


# ============================================================================
# Test: Path Rewriting
# ============================================================================


class TestPathRewriting:
    """Tests for request path rewriting."""

    def test_rewrite_chatgpt_responses_paths(self):
        """ChatGPT responses paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path

        assert (
            rewrite_request_path(
                req_path="/responses",
                upstream_host="chatgpt.com",
                upstream_base_path="/backend-api",
            )
            == "/codex/responses"
        )

    def test_rewrite_chatgpt_v1_responses_paths(self):
        """ChatGPT v1/responses paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path

        assert (
            rewrite_request_path(
                req_path="/v1/responses",
                upstream_host="chatgpt.com",
                upstream_base_path="/backend-api",
            )
            == "/codex/responses"
        )

    def test_rewrite_compact_paths(self):
        """Compact paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path

        assert (
            rewrite_request_path(
                req_path="/v1/responses/compact",
                upstream_host="chat.openai.com",
                upstream_base_path="/backend-api",
            )
            == "/codex/responses/compact"
        )

    def test_no_rewrite_for_other_upstreams(self):
        """Other upstreams should not have paths rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path

        assert (
            rewrite_request_path(
                req_path="/responses",
                upstream_host="api.openai.com",
                upstream_base_path="/v1",
            )
            == "/responses"
        )


# ============================================================================
# Test: Header Handling
# ============================================================================


class TestHeaderHandling:
    """Tests for header manipulation."""

    def test_set_header_case_insensitive_adds_new(self):
        """set_header_case_insensitive should add new headers."""
        from cdx_proxy_cli_v2.proxy.rules import set_header_case_insensitive

        headers = {"Content-Type": "application/json"}
        set_header_case_insensitive(headers, "Authorization", "Bearer token")
        assert headers["Authorization"] == "Bearer token"

    def test_set_header_case_insensitive_replaces_existing(self):
        """set_header_case_insensitive should replace existing headers case-insensitively."""
        from cdx_proxy_cli_v2.proxy.rules import set_header_case_insensitive

        headers = {"authorization": "old-token"}
        set_header_case_insensitive(headers, "Authorization", "new-token")
        assert "authorization" not in headers
        assert headers["Authorization"] == "new-token"

    def test_drop_header_case_insensitive(self):
        """drop_header_case_insensitive should remove headers case-insensitively."""
        from cdx_proxy_cli_v2.proxy.rules import drop_header_case_insensitive

        headers = {"Content-Type": "application/json", "content-length": "100"}
        drop_header_case_insensitive(headers, "content-type")
        assert "Content-Type" not in headers
        assert "content-length" in headers

    def test_chatgpt_backend_headers_are_replaced_case_insensitively(
        self, test_settings, sample_auth_record
    ):
        """ChatGPT backend should replace conflicting header variants with canonical values."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            sample_auth_record,
        )
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/conversation",
            headers={
                "Origin": "https://app.example.com",
                "origin": "https://lower.example.com",
                "Referer": "https://app.example.com/chat",
                "referer": "https://lower.example.com/chat",
                "User-Agent": "Desktop Browser",
                "user-agent": "mobile-browser",
                "X-Trace-Id": "trace-123",
            },
        )
        captured_headers: Dict[str, str] = {}

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            captured_headers.update(dict(kwargs["headers"]))
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b"{}",
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)

        handler._proxy_request()

        assert captured_headers["Origin"] == "https://chatgpt.com"
        assert captured_headers["Referer"] == "https://chatgpt.com/"
        assert captured_headers["User-Agent"] == "codex-cli"
        assert "origin" not in captured_headers
        assert "referer" not in captured_headers
        assert "user-agent" not in captured_headers
        assert captured_headers["X-Trace-Id"] == "trace-123"
        assert captured_headers["Authorization"] == f"Bearer {sample_auth_record.token}"
        assert captured_headers["chatgpt-account-id"] == str(
            sample_auth_record.account_id
        )

    def test_non_chatgpt_backend_preserves_caller_header_variants(
        self, test_settings, sample_auth_record
    ):
        """Non-ChatGPT upstreams should keep caller-provided header casing and values."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://api.example.com/v1"),
            sample_auth_record,
        )
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/conversation",
            headers={
                "Origin": "https://app.example.com",
                "origin": "https://lower.example.com",
                "Referer": "https://app.example.com/chat",
                "referer": "https://lower.example.com/chat",
                "User-Agent": "Desktop Browser",
                "user-agent": "mobile-browser",
                "X-Trace-Id": "trace-123",
            },
        )
        captured_headers: Dict[str, str] = {}

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            captured_headers.update(dict(kwargs["headers"]))
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b"{}",
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)

        handler._proxy_request()

        assert captured_headers["Origin"] == "https://app.example.com"
        assert captured_headers["origin"] == "https://lower.example.com"
        assert captured_headers["Referer"] == "https://app.example.com/chat"
        assert captured_headers["referer"] == "https://lower.example.com/chat"
        assert captured_headers["User-Agent"] == "Desktop Browser"
        assert captured_headers["user-agent"] == "mobile-browser"
        assert captured_headers["X-Trace-Id"] == "trace-123"
        assert captured_headers["Authorization"] == f"Bearer {sample_auth_record.token}"
        assert "chatgpt-account-id" not in captured_headers

    def test_chatgpt_backend_rewrites_incompatible_model_ids(
        self, test_settings, sample_auth_record
    ):
        """ChatGPT backend should normalize unsupported model ids before forwarding."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            sample_auth_record,
        )
        body = json.dumps({"model": "gpt-5.4", "input": "Hello"}).encode("utf-8")
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        captured_body: Dict[str, Any] = {}

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            captured_body.update(json.loads(kwargs["body"].decode("utf-8")))
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b"{}",
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)

        handler._proxy_request()

        assert captured_body["model"] == "gpt-5.1-codex-max"
        assert captured_body["input"] == "Hello"

    def test_non_chatgpt_backend_preserves_model_id(
        self, test_settings, sample_auth_record
    ):
        """Non-ChatGPT upstreams should forward the caller model unchanged."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://api.example.com/v1"),
            sample_auth_record,
        )
        body = json.dumps({"model": "gpt-5.4", "input": "Hello"}).encode("utf-8")
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        captured_body: Dict[str, Any] = {}

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            captured_body.update(json.loads(kwargs["body"].decode("utf-8")))
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b"{}",
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)

        handler._proxy_request()

        assert captured_body["model"] == "gpt-5.4"
        assert captured_body["input"] == "Hello"

    def test_chatgpt_websocket_upgrade_preserves_upgrade_headers(
        self, test_settings, sample_auth_record
    ):
        """ChatGPT websocket upgrade requests should keep the handshake headers."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            sample_auth_record,
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
        captured_headers: Dict[str, str] = {}

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            captured_headers.update(dict(kwargs["headers"]))
            return UpstreamAttemptResult(
                status=405,
                headers=[("Content-Type", "application/json")],
                body=b'{"detail":"Method Not Allowed"}',
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)

        handler._proxy_request()

        assert captured_headers["Connection"] == "Upgrade"
        assert captured_headers["Upgrade"] == "websocket"
        assert captured_headers["Sec-WebSocket-Key"] == "test-key"
        assert captured_headers["Sec-WebSocket-Version"] == "13"
        assert captured_headers["Origin"] == "https://chatgpt.com"
        assert captured_headers["Referer"] == "https://chatgpt.com/"
        assert captured_headers["User-Agent"] == "codex-cli"


# ============================================================================
# Test: Models Endpoint
# ============================================================================


class TestModelsEndpoint:
    """Tests for the synthetic /backend-api/models endpoint."""

    def test_returns_chatgpt_account_supported_models(
        self, test_settings, sample_auth_record
    ):
        """Models endpoint should advertise only ChatGPT-account-compatible models."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://chatgpt.com/backend-api"),
            sample_auth_record,
        )
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/backend-api/models",
            headers={},
            method="GET",
        )

        handler._handle_models_endpoint()

        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert [item["id"] for item in payload["data"]] == [
            "gpt-5.1-codex-max",
            "gpt-5.1-codex",
            "gpt-5.1-codex-mini",
        ]
        assert all(item["display_name"] for item in payload["data"])
        assert all(item["shell_type"] == "shell_command" for item in payload["data"])
        assert all(item["visibility"] == "list" for item in payload["data"])

    def test_normalizes_upstream_models_payload_for_codex_cli(self):
        """Upstream /models payloads should gain display_name for CLI compatibility."""
        body = json.dumps(
            {
                "models": [
                    {"slug": "gpt-5-3", "title": "GPT-5.3"},
                    {"slug": "gpt-5-mini"},
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path="/models?client_version=0.114.0"
            ).decode("utf-8")
        )

        assert normalized["models"][0]["display_name"] == "GPT-5.3"
        assert normalized["models"][1]["display_name"] == "gpt-5-mini"

    def test_normalizes_supported_reasoning_levels_for_codex_cli(self):
        """Upstream /models payloads should expose supported_reasoning_levels."""
        body = json.dumps(
            {
                "models": [
                    {
                        "slug": "gpt-5-4-thinking",
                        "title": "GPT-5.4 Thinking",
                        "thinking_efforts": [
                            {"thinking_effort": "standard"},
                            {"thinking_effort": "extended"},
                        ],
                    },
                    {
                        "slug": "gpt-5-3-instant",
                        "title": "GPT-5.3 Instant",
                        "reasoning_type": "none",
                    },
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path="/models?client_version=0.114.0"
            ).decode("utf-8")
        )

        assert normalized["models"][0]["supported_reasoning_levels"] == [
            {"effort": "standard", "description": "standard"},
            {"effort": "extended", "description": "extended"},
        ]
        assert normalized["models"][1]["supported_reasoning_levels"] == []

    def test_normalizes_shell_type_for_codex_cli(self):
        """Upstream /models payloads should expose Codex-required fields."""
        body = json.dumps(
            {
                "models": [
                    {"slug": "gpt-5-3", "title": "GPT-5.3", "max_tokens": 64000},
                    {"slug": "gpt-5", "title": "GPT-5"},
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path="/models?client_version=0.114.0"
            ).decode("utf-8")
        )

        assert normalized["models"][0]["shell_type"] == "shell_command"
        assert normalized["models"][1]["shell_type"] == "default"
        assert normalized["models"][0]["visibility"] == "list"
        assert normalized["models"][0]["supported_in_api"] is True
        assert normalized["models"][0]["priority"] == 0
        assert normalized["models"][0]["default_reasoning_level"] == "low"
        assert normalized["models"][0]["context_window"] == 64000
        assert normalized["models"][0]["input_modalities"] == ["text"]
        assert normalized["models"][0]["truncation_policy"] == {
            "mode": "tokens",
            "limit": 10000,
        }
        assert normalized["models"][0]["model_messages"] == {
            "instructions_template": ""
        }
        assert normalized["models"][1]["default_reasoning_level"] == "low"


class TestMergedHealth:
    """Tests for merged runtime + limit health output."""

    def test_health_snapshot_respects_limit_cooldown(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)

        with patch("cdx_proxy_cli_v2.proxy.server.fetch_limit_health") as mock_limits:
            mock_limits.return_value = {
                sample_auth_record.name: {
                    "file": sample_auth_record.name,
                    "status": "COOLDOWN",
                    "weekly": {
                        "status": "COOLDOWN",
                        "used_percent": 100.0,
                        "reset_after_seconds": 300,
                    },
                }
            }
            snapshot = runtime.health_snapshot(refresh=False)

        assert snapshot["ok"] is False
        assert snapshot["accounts"][0]["status"] == "COOLDOWN"
        assert snapshot["accounts"][0]["reason"] == "limit_weekly"
        assert snapshot["accounts"][0]["reason_origin"] == "limit"
        assert snapshot["accounts"][0]["eligible_now"] is False


class TestRuntimeTransitionsAndOverload:
    """Tests for KISS runtime transitions and local overload handling."""

    def test_overloaded_request_returns_503_without_touching_auth_pool(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(
            replace(test_settings, max_in_flight_requests=1, max_pending_requests=0),
            sample_auth_record,
        )
        lease = runtime.overload_guard.acquire()
        assert lease.admitted is True
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b"{}",
            )
        )
        before = runtime.auth_pool.health_snapshot()
        try:
            handler._proxy_request()
        finally:
            lease.release()
        after = runtime.auth_pool.health_snapshot()

        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert payload["error"] == "proxy overloaded"
        assert before == after
        handler._run_upstream_attempt.assert_not_called()
        assert any(
            event.get("event") == "proxy.overloaded"
            for event in runtime.trace_store.list(limit=20)
        )

    def test_proxy_request_logs_auth_cooldown_transition(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=401,
                headers=[("Content-Type", "application/json")],
                body=b'{"error":{"code":"token_invalid"}}',
                error_code="token_invalid",
            )
        )

        handler._proxy_request()

        events = runtime.trace_store.list(limit=20)
        assert any(event.get("event") == "auth.cooldown" for event in events)
        assert not any(event.get("event") == "auth.blacklisted" for event in events)
        assert not any(event.get("event") == "auth.ejected" for event in events)

    def test_non_auth_4xx_does_not_cooldown_auth(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/responses",
            method="GET",
            headers={},
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=405,
                headers=[("Content-Type", "application/json")],
                body=b'{"detail":"Method Not Allowed"}',
            )
        )

        handler._proxy_request()

        snapshot = runtime.auth_pool.health_snapshot()[0]
        events = runtime.trace_store.list(limit=20)
        assert snapshot["status"] == "OK"
        assert not any(event.get("event") == "auth.cooldown" for event in events)

    def test_proxy_request_logs_auth_ejected_transition_at_threshold(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = _build_runtime(
            replace(test_settings, consecutive_error_threshold=1),
            sample_auth_record,
        )
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=401,
                headers=[("Content-Type", "application/json")],
                body=b'{"error":{"code":"token_invalid"}}',
                error_code="token_invalid",
            )
        )

        handler._proxy_request()

        events = runtime.trace_store.list(limit=20)
        assert any(event.get("event") == "auth.ejected" for event in events)
        assert not any(event.get("event") == "auth.blacklisted" for event in events)

    def test_debug_payload_includes_overload_limits_and_metrics(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(
            replace(test_settings, max_in_flight_requests=3, max_pending_requests=2),
            sample_auth_record,
        )

        payload = runtime.debug_payload(host="127.0.0.1", port=43123)

        assert payload["max_in_flight_requests"] == 3
        assert payload["max_pending_requests"] == 2
        metrics = payload["metrics"]
        assert metrics["requests_total"] == 0
        assert metrics["upstream_errors_total"] == 0
        assert metrics["auth_ejections_total"] == 0
        assert metrics["auth_restores_total"] == 0
        assert metrics["auth_available"] == 1
        assert metrics["in_flight_requests"] == 0


class TestProbeBehavior:
    """Tests for non-destructive probe behavior."""

    def test_probe_all_auths_does_not_mutate_runtime_state(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        before = runtime.auth_pool.health_snapshot()

        with patch(
            "cdx_proxy_cli_v2.proxy.server.load_auth_records",
            return_value=[sample_auth_record],
        ):
            runtime._probe_single_auth = MagicMock(
                return_value={
                    "file": sample_auth_record.name,
                    "success": False,
                    "http_status": 403,
                    "error_code": "forbidden",
                    "latency_ms": 7,
                }
            )

            result = runtime.probe_all_auths(timeout=5)
        after = runtime.auth_pool.health_snapshot()

        assert result["results"][0]["action"] == "auth_failed"
        assert before == after

    def test_probe_single_auth_uses_chatgpt_backend_headers(
        self, test_settings, sample_auth_record
    ):
        settings = replace(test_settings, upstream="https://chatgpt.com/backend-api")
        runtime = _build_runtime(settings, sample_auth_record)

        mock_connection = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"{}"
        mock_connection.getresponse.return_value = mock_response

        with patch("http.client.HTTPSConnection", return_value=mock_connection):
            result = runtime._probe_single_auth(
                sample_auth_record.name,
                sample_auth_record.token,
                sample_auth_record.account_id,
                timeout=5,
            )

        headers = mock_connection.request.call_args.kwargs["headers"]
        assert result["success"] is True
        assert headers["Authorization"] == f"Bearer {sample_auth_record.token}"
        assert headers["ChatGPT-Account-Id"] == sample_auth_record.account_id
        assert headers["Origin"] == "https://chatgpt.com"
        assert headers["Referer"] == "https://chatgpt.com/"
        assert headers["User-Agent"] == "codex-cli"

    def test_single_upstream_5xx_increments_error_metric(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/v1/responses",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=502,
                headers=[("Content-Type", "application/json")],
                body=b'{"error":"bad gateway"}',
                error_code="upstream_request_failed",
            )
        )

        handler._proxy_request()

        assert runtime.metrics_snapshot()["upstream_errors_total"] == 1


# ============================================================================
# Test: Loopback Host Detection
# ============================================================================


class TestLoopbackHostDetection:
    """Tests for loopback host detection."""

    def test_localhost_is_loopback(self):
        """'localhost' should be detected as loopback."""
        from cdx_proxy_cli_v2.proxy.rules import is_loopback_host

        assert is_loopback_host("localhost") is True

    def test_127_ip_is_loopback(self):
        """127.x.x.x should be detected as loopback."""
        from cdx_proxy_cli_v2.proxy.rules import is_loopback_host

        assert is_loopback_host("127.0.0.1") is True
        assert is_loopback_host("127.0.0.100") is True

    def test_non_loopback_detected(self):
        """Non-loopback addresses should not be detected as loopback."""
        from cdx_proxy_cli_v2.proxy.rules import is_loopback_host

        assert is_loopback_host("192.168.1.1") is False
        assert is_loopback_host("10.0.0.1") is False
        assert is_loopback_host("example.com") is False


# ============================================================================
# Test: Retry Logic
# ============================================================================


class TestRetryLogic:
    """Tests for auth retry logic on failures."""

    def test_401_triggers_blacklist(self, mock_auth_pool):
        """401 response should blacklist the auth."""
        mock_auth_pool.mark_result(
            "test_auth.json", status=401, error_code="token_invalid"
        )

        stats = mock_auth_pool.stats()
        assert stats["ok"] == 0

    def test_429_triggers_cooldown(self, mock_auth_pool):
        """429 response should trigger cooldown."""
        mock_auth_pool.mark_result("test_auth.json", status=429)

        stats = mock_auth_pool.stats()
        assert stats["cooldown"] == 1

    def test_200_clears_cooldown(self, mock_auth_pool):
        """200 response should clear cooldown."""
        # First trigger cooldown
        mock_auth_pool.mark_result("test_auth.json", status=429)

        # Then success
        mock_auth_pool.mark_result("test_auth.json", status=200)

        stats = mock_auth_pool.stats()
        assert stats["ok"] == 1

    def test_403_triggers_blacklist(self, mock_auth_pool):
        """403 response should blacklist the auth."""
        mock_auth_pool.mark_result("test_auth.json", status=403, error_code="forbidden")

        stats = mock_auth_pool.stats()
        assert stats["ok"] == 0

    def test_400_account_incompatibility_triggers_blacklist(self, mock_auth_pool):
        """Known account-incompatible 400s should blacklist the auth immediately."""
        mock_auth_pool.mark_result(
            "test_auth.json", status=400, error_code="chatgpt_account_incompatible"
        )

        stats = mock_auth_pool.stats()
        assert stats["ok"] == 0


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
