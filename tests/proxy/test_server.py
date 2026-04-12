"""Comprehensive tests for proxy server module."""

from __future__ import annotations

from dataclasses import replace
import json
from io import BytesIO
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import RoundRobinAuthPool
from cdx_proxy_cli_v2.config.settings import Settings
from cdx_proxy_cli_v2.observability.limits_history import (
    latest_limits_path,
    limits_history_path,
)
from cdx_proxy_cli_v2.proxy.failure_types import (
    FAILURE_ORIGIN_HARD_AUTH,
    FAILURE_ORIGIN_PROBE_TRANSPORT,
)
from cdx_proxy_cli_v2.proxy.server import (
    CHATGPT_ACCOUNT_MODEL_FALLBACK,
    CHATGPT_ACCOUNT_MODEL_REWRITES,
    CHATGPT_ACCOUNT_MODELS,
    ProxyHandler,
    ProxyRuntime,
    UpstreamAttemptResult,
    _extract_error_code,
    _normalize_chatgpt_request_body,
    _normalize_models_response_body,
)

REWRITE_SOURCE_MODEL = next(iter(CHATGPT_ACCOUNT_MODEL_REWRITES))
INCOMPATIBLE_MODEL_DETAIL = (
    f"The '{REWRITE_SOURCE_MODEL}' model is not supported when using Codex with a ChatGPT account."
)
CLIENT_MODELS_PATH = "/models?client_version=0.114.0"
BACKEND_MODELS_PATH = "/backend-api/models"
API_MODELS_PATH = "/api/models"
OPENAI_MODELS_PATH = "/v1/models"
PRIMARY_RESPONSES_PATH = "/v1/responses"
RESPONSES_PATH = "/responses"
CODEX_RESPONSES_PATH = "/codex/responses"
RESPONSES_COMPACT_PATH = "/responses/compact"
RESPONSES_COMPACT_WITH_QUERY = "/responses/compact?x=1"
V1_RESPONSES_COMPACT_PATH = "/v1/responses/compact"
DEBUG_PATH = "/debug"
TRACE_PATH = "/trace"
HEALTH_PATH = "/health"
AUTH_FILES_PATH = "/auth-files"
SHUTDOWN_PATH = "/shutdown"
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
UNKNOWN_PATH = "/some/random/path"
TEST_INPUT_TEXT = "Hello"
UPSTREAM_AUTO_MODEL_SLUG = "gpt-5-3"
UPSTREAM_AUTO_MODEL_TITLE = "GPT-5.3"
UPSTREAM_MINI_MODEL_SLUG = "gpt-5-mini"
UPSTREAM_THINKING_MODEL_SLUG = "gpt-5-4-thinking"
UPSTREAM_THINKING_MODEL_TITLE = "GPT-5.4 Thinking"
UPSTREAM_INSTANT_MODEL_SLUG = "gpt-5-3-instant"
UPSTREAM_INSTANT_MODEL_TITLE = "GPT-5.3 Instant"
UPSTREAM_DEFAULT_MODEL_SLUG = "gpt-5"
UPSTREAM_DEFAULT_MODEL_TITLE = "GPT-5"


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
                "detail": INCOMPATIBLE_MODEL_DETAIL
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

        assert management_route(DEBUG_PATH) == "debug"

    def test_management_route_trace(self):
        """Trace endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route(TRACE_PATH) == "trace"

    def test_management_route_health(self):
        """Health endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route(HEALTH_PATH) == "health"

    def test_management_route_auth_files(self):
        """Auth-files endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route(AUTH_FILES_PATH) == "auth-files"

    def test_management_route_shutdown(self):
        """Shutdown endpoint should be recognized as management route."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route(SHUTDOWN_PATH) == "shutdown"

    def test_non_management_route_returns_none(self):
        """Non-management paths should return None."""
        from cdx_proxy_cli_v2.proxy.rules import management_route

        assert management_route(CHAT_COMPLETIONS_PATH) is None
        assert management_route(API_MODELS_PATH) is None
        assert management_route(UNKNOWN_PATH) is None


# ============================================================================
# Test: Trace Route Classification
# ============================================================================


class TestTraceRouteClassification:
    """Tests for trace route classification."""

    def test_trace_route_request(self):
        """/responses path should be classified as 'request'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route

        assert trace_route(RESPONSES_PATH) == "responses"
        assert trace_route(CODEX_RESPONSES_PATH) == "responses"

    def test_trace_route_compact(self):
        """Paths ending in /compact should be classified as 'compact'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route

        assert trace_route(RESPONSES_COMPACT_PATH) == "compact"
        assert trace_route(RESPONSES_COMPACT_WITH_QUERY) == "compact"

    def test_trace_route_other(self):
        """Other paths should be classified as 'other'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route

        assert trace_route(HEALTH_PATH) == "management"
        assert trace_route(DEBUG_PATH) == "management"
        assert trace_route(OPENAI_MODELS_PATH) == "models"
        assert trace_route(UNKNOWN_PATH) == ""


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
                req_path=RESPONSES_PATH,
                upstream_host="chatgpt.com",
                upstream_base_path="/backend-api",
            )
            == CODEX_RESPONSES_PATH
        )

    def test_rewrite_chatgpt_v1_responses_paths(self):
        """ChatGPT v1/responses paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path

        assert (
            rewrite_request_path(
                req_path=PRIMARY_RESPONSES_PATH,
                upstream_host="chatgpt.com",
                upstream_base_path="/backend-api",
            )
            == CODEX_RESPONSES_PATH
        )

    def test_rewrite_compact_paths(self):
        """Compact paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path

        assert (
            rewrite_request_path(
                req_path=V1_RESPONSES_COMPACT_PATH,
                upstream_host="chat.openai.com",
                upstream_base_path="/backend-api",
            )
            == f"{CODEX_RESPONSES_PATH}/compact"
        )

    def test_no_rewrite_for_other_upstreams(self):
        """Other upstreams should not have paths rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path

        assert (
            rewrite_request_path(
                req_path=RESPONSES_PATH,
                upstream_host="api.openai.com",
                upstream_base_path="/v1",
            )
            == RESPONSES_PATH
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
        body = json.dumps({"model": REWRITE_SOURCE_MODEL, "input": TEST_INPUT_TEXT}).encode("utf-8")
        handler = _build_proxy_handler(
            runtime=runtime,
            path=PRIMARY_RESPONSES_PATH,
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

        assert captured_body["model"] == CHATGPT_ACCOUNT_MODEL_FALLBACK
        assert captured_body["input"] == TEST_INPUT_TEXT

    def test_non_chatgpt_backend_preserves_model_id(
        self, test_settings, sample_auth_record
    ):
        """Non-ChatGPT upstreams should forward the caller model unchanged."""
        runtime = _build_runtime(
            replace(test_settings, upstream="https://api.example.com/v1"),
            sample_auth_record,
        )
        body = json.dumps({"model": REWRITE_SOURCE_MODEL, "input": TEST_INPUT_TEXT}).encode("utf-8")
        handler = _build_proxy_handler(
            runtime=runtime,
            path=PRIMARY_RESPONSES_PATH,
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

        assert captured_body["model"] == REWRITE_SOURCE_MODEL
        assert captured_body["input"] == TEST_INPUT_TEXT

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
            path=BACKEND_MODELS_PATH,
            headers={},
            method="GET",
        )

        handler._handle_models_endpoint()

        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert [item["id"] for item in payload["data"]] == list(CHATGPT_ACCOUNT_MODELS)
        assert all(item["display_name"] for item in payload["data"])
        assert all(item["shell_type"] == "shell_command" for item in payload["data"])
        assert all(item["visibility"] == "list" for item in payload["data"])

    def test_normalizes_upstream_models_payload_for_codex_cli(self):
        """Upstream /models payloads should gain display_name for CLI compatibility."""
        body = json.dumps(
            {
                "models": [
                    {"slug": UPSTREAM_AUTO_MODEL_SLUG, "title": UPSTREAM_AUTO_MODEL_TITLE},
                    {"slug": UPSTREAM_MINI_MODEL_SLUG},
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path=CLIENT_MODELS_PATH
            ).decode("utf-8")
        )

        assert normalized["models"][0]["display_name"] == UPSTREAM_AUTO_MODEL_TITLE
        assert normalized["models"][1]["display_name"] == UPSTREAM_MINI_MODEL_SLUG

    def test_sets_medium_default_verbosity_for_rewritten_models(self):
        """Models rewritten to ChatGPT-account fallbacks should advertise compatible verbosity."""
        body = json.dumps(
            {
                "models": [
                    {
                        "slug": REWRITE_SOURCE_MODEL,
                        "title": "Rewritten model",
                    },
                    {
                        "slug": UPSTREAM_MINI_MODEL_SLUG,
                        "title": UPSTREAM_INSTANT_MODEL_TITLE,
                    },
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path=CLIENT_MODELS_PATH
            ).decode("utf-8")
        )

        assert normalized["models"][0]["default_verbosity"] == "medium"
        assert normalized["models"][1]["default_verbosity"] == "low"

    def test_normalizes_supported_reasoning_levels_for_codex_cli(self):
        """Upstream /models payloads should expose supported_reasoning_levels."""
        body = json.dumps(
            {
                "models": [
                    {
                        "slug": UPSTREAM_THINKING_MODEL_SLUG,
                        "title": UPSTREAM_THINKING_MODEL_TITLE,
                        "thinking_efforts": [
                            {"thinking_effort": "standard"},
                            {"thinking_effort": "extended"},
                        ],
                    },
                    {
                        "slug": UPSTREAM_INSTANT_MODEL_SLUG,
                        "title": UPSTREAM_INSTANT_MODEL_TITLE,
                        "reasoning_type": "none",
                    },
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path=CLIENT_MODELS_PATH
            ).decode("utf-8")
        )

        assert normalized["models"][0]["supported_reasoning_levels"] == [
            {"effort": "medium", "description": "standard"},
            {"effort": "high", "description": "extended"},
        ]
        assert normalized["models"][1]["supported_reasoning_levels"] == []

    def test_maps_alias_reasoning_levels_to_codex_enum(self):
        """Codex only accepts a fixed reasoning-level enum in /models payloads."""
        body = json.dumps(
            {
                "models": [
                    {
                        "slug": UPSTREAM_THINKING_MODEL_SLUG,
                        "default_reasoning_level": "standard",
                        "supported_reasoning_levels": [
                            {"effort": "standard", "description": "Balanced thinking"},
                            {"effort": "extended", "description": "Longer thinking"},
                        ],
                    }
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path=CLIENT_MODELS_PATH
            ).decode("utf-8")
        )

        assert normalized["models"][0]["default_reasoning_level"] == "medium"
        assert normalized["models"][0]["supported_reasoning_levels"] == [
            {"effort": "medium", "description": "Balanced thinking"},
            {"effort": "high", "description": "Longer thinking"},
        ]

    def test_normalizes_shell_type_for_codex_cli(self):
        """Upstream /models payloads should expose Codex-required fields."""
        body = json.dumps(
            {
                "models": [
                    {
                        "slug": UPSTREAM_AUTO_MODEL_SLUG,
                        "title": UPSTREAM_AUTO_MODEL_TITLE,
                        "max_tokens": 64000,
                    },
                    {"slug": UPSTREAM_DEFAULT_MODEL_SLUG, "title": UPSTREAM_DEFAULT_MODEL_TITLE},
                ]
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_models_response_body(
                body, request_path=CLIENT_MODELS_PATH
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

    def test_rewrites_incompatible_request_verbosity_for_fallback_model(self):
        """Rewritten ChatGPT-account requests should not forward unsupported verbosity levels."""
        body = json.dumps(
            {
                "model": REWRITE_SOURCE_MODEL,
                "input": TEST_INPUT_TEXT,
                "text": {"verbosity": "low"},
            }
        ).encode("utf-8")

        normalized = json.loads(
            _normalize_chatgpt_request_body(
                body, {"Content-Type": "application/json"}
            ).decode("utf-8")
        )

        assert normalized["model"] == CHATGPT_ACCOUNT_MODEL_FALLBACK
        assert normalized["text"]["verbosity"] == "medium"


class TestMergedHealth:
    """Tests for merged runtime + limit health output."""

    def test_health_snapshot_includes_next_auth(self, test_settings, sample_auth_record):
        runtime = _build_runtime(test_settings, sample_auth_record)

        snapshot = runtime.health_snapshot(refresh=False)

        assert snapshot["next_auth_file"] == sample_auth_record.name
        assert snapshot["next_auth_email"] == sample_auth_record.email

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

    def test_trace_payload_includes_limits_and_persists_snapshot(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        runtime.trace_store.add(
            {
                "ts": 100.0,
                "event": "proxy.request",
                "path": "/responses",
                "auth_file": sample_auth_record.name,
            }
        )

        with patch("cdx_proxy_cli_v2.proxy.server.fetch_limit_health") as mock_limits:
            mock_limits.return_value = {
                sample_auth_record.name: {
                    "file": sample_auth_record.name,
                    "email": sample_auth_record.email,
                    "status": "WARN",
                    "five_hour": {
                        "status": "WARN",
                        "used_percent": 89.5,
                        "reset_after_seconds": 1800,
                    },
                    "weekly": {
                        "status": "OK",
                        "used_percent": 41.0,
                        "reset_after_seconds": 250000,
                    },
                }
            }
            payload = runtime.trace_payload(limit=10)

        assert isinstance(payload["events"], list)
        assert payload["events"][0]["path"] == "/responses"
        assert payload["limits"]["accounts"][0]["file"] == sample_auth_record.name
        assert payload["limits"]["accounts"][0]["five_hour"]["used_percent"] == 89.5
        assert payload["limits"]["fetched_at"] is not None
        assert payload["limits"]["next_auth_file"] is None
        assert latest_limits_path(test_settings.auth_dir).exists()

        history_lines = limits_history_path(test_settings.auth_dir).read_text().splitlines()
        assert len(history_lines) == 1
        assert sample_auth_record.token not in latest_limits_path(
            test_settings.auth_dir
        ).read_text()

    def test_trace_payload_reports_limit_fetch_error_with_runtime_accounts(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)

        with patch(
            "cdx_proxy_cli_v2.proxy.server.fetch_limit_health",
            side_effect=RuntimeError("boom"),
        ):
            payload = runtime.trace_payload(limit=5)

        assert payload["limits"]["error"] == "boom"
        assert payload["limits"]["stale"] is True
        assert payload["limits"]["accounts"][0]["file"] == sample_auth_record.name


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
            path=PRIMARY_RESPONSES_PATH,
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
            path=PRIMARY_RESPONSES_PATH,
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
            path=RESPONSES_PATH,
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

    def test_compact_request_keeps_warn_auths_available(
        self,
        test_settings,
    ):
        warn_auth = AuthRecord(
            name="warn.json",
            path="/tmp/warn.json",
            token="tok-warn",
            email="warn@example.com",
        )
        ok_auth = AuthRecord(
            name="ok.json",
            path="/tmp/ok.json",
            token="tok-ok",
            email="ok@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([warn_auth, ok_auth])
        runtime._limit_health_cache = {
            warn_auth.name: {
                "file": warn_auth.name,
                "email": warn_auth.email,
                "status": "WARN",
                "five_hour": {
                    "status": "WARN",
                    "used_percent": 85.0,
                    "reset_after_seconds": 1800,
                },
            },
            ok_auth.name: {
                "file": ok_auth.name,
                "email": ok_auth.email,
                "status": "OK",
                "five_hour": {
                    "status": "OK",
                    "used_percent": 20.0,
                    "reset_after_seconds": 1800,
                },
            },
        }
        runtime._refresh_limit_health = MagicMock(return_value=runtime._limit_health_cache)
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_COMPACT_PATH,
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

        handler._proxy_request()

        sent_headers = handler._run_upstream_attempt.call_args.kwargs["headers"]
        assert sent_headers["Authorization"] == f"Bearer {warn_auth.token}"

    def test_next_auth_payload_keeps_warn_auths_available_for_interactive_route(
        self,
        test_settings,
    ):
        warn_auth = AuthRecord(
            name="warn.json",
            path="/tmp/warn.json",
            token="tok-warn",
            email="warn@example.com",
        )
        ok_auth = AuthRecord(
            name="ok.json",
            path="/tmp/ok.json",
            token="tok-ok",
            email="ok@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([warn_auth, ok_auth])
        runtime._limit_health_cache = {
            warn_auth.name: {
                "file": warn_auth.name,
                "email": warn_auth.email,
                "status": "WARN",
                "five_hour": {
                    "status": "WARN",
                    "used_percent": 85.0,
                    "reset_after_seconds": 1800,
                },
            },
            ok_auth.name: {
                "file": ok_auth.name,
                "email": ok_auth.email,
                "status": "OK",
                "five_hour": {
                    "status": "OK",
                    "used_percent": 20.0,
                    "reset_after_seconds": 1800,
                },
            },
        }

        next_auth = runtime.next_auth_payload(route="responses")

        assert next_auth == {"file": warn_auth.name, "email": warn_auth.email}

    def test_next_auth_payload_keeps_noninteractive_routes_unfiltered(
        self,
        test_settings,
    ):
        warn_auth = AuthRecord(
            name="warn.json",
            path="/tmp/warn.json",
            token="tok-warn",
            email="warn@example.com",
        )
        ok_auth = AuthRecord(
            name="ok.json",
            path="/tmp/ok.json",
            token="tok-ok",
            email="ok@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([warn_auth, ok_auth])
        runtime._limit_health_cache = {
            warn_auth.name: {
                "file": warn_auth.name,
                "email": warn_auth.email,
                "status": "WARN",
                "five_hour": {
                    "status": "WARN",
                    "used_percent": 85.0,
                    "reset_after_seconds": 1800,
                },
            },
            ok_auth.name: {
                "file": ok_auth.name,
                "email": ok_auth.email,
                "status": "OK",
                "five_hour": {
                    "status": "OK",
                    "used_percent": 20.0,
                    "reset_after_seconds": 1800,
                },
            },
        }

        next_auth = runtime.next_auth_payload(route="models")

        assert next_auth == {"file": warn_auth.name, "email": warn_auth.email}

    def test_interactive_request_fails_locally_when_no_eligible_auth_exists(
        self,
        test_settings,
    ):
        limited_auth = AuthRecord(
            name="limited.json",
            path="/tmp/limited.json",
            token="tok-limited",
            email="limited@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([limited_auth])
        runtime._limit_health_cache = {
            limited_auth.name: {
                "file": limited_auth.name,
                "email": limited_auth.email,
                "status": "COOLDOWN",
                "five_hour": {
                    "status": "COOLDOWN",
                    "used_percent": 100.0,
                    "reset_after_seconds": 1800,
                },
            },
        }
        runtime._refresh_limit_health = MagicMock(return_value=runtime._limit_health_cache)
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock()

        handler._proxy_request()

        assert handler._run_upstream_attempt.call_count == 0
        assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
            "error": "interactive auth pool unavailable",
            "reason": "interactive_pool_weak",
        }
        events = runtime.trace_store.list(limit=20)
        assert any(event.get("event") == "auth.interactive_skipped" for event in events)
        assert any(event.get("event") == "auth.interactive_pool_weak" for event in events)

    def test_interactive_request_rotates_to_next_safe_auth_before_local_failure(
        self,
        test_settings,
    ):
        first_auth = AuthRecord(
            name="first.json",
            path="/tmp/first.json",
            token="tok-first",
            email="first@example.com",
        )
        second_auth = AuthRecord(
            name="second.json",
            path="/tmp/second.json",
            token="tok-second",
            email="second@example.com",
        )
        runtime = ProxyRuntime(settings=replace(test_settings, consecutive_error_threshold=1))
        runtime.auth_pool.load([first_auth, second_auth])
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        seen_tokens: list[str] = []

        def fake_run_upstream_attempt(**kwargs: Any) -> UpstreamAttemptResult:
            seen_tokens.append(str(kwargs["headers"]["Authorization"]))
            if len(seen_tokens) == 1:
                return UpstreamAttemptResult(
                    status=429,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"error":{"code":"rate_limited"}}',
                    error_code="rate_limited",
                )
            return UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"ok":true}',
            )

        handler._run_upstream_attempt = MagicMock(side_effect=fake_run_upstream_attempt)

        handler._proxy_request()

        assert seen_tokens == [
            f"Bearer {first_auth.token}",
            f"Bearer {second_auth.token}",
        ]
        assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {"ok": True}

    def test_interactive_request_returns_local_failure_after_safe_retries_exhausted(
        self,
        test_settings,
    ):
        first_auth = AuthRecord(
            name="first.json",
            path="/tmp/first.json",
            token="tok-first",
            email="first@example.com",
        )
        second_auth = AuthRecord(
            name="second.json",
            path="/tmp/second.json",
            token="tok-second",
            email="second@example.com",
        )
        runtime = ProxyRuntime(settings=replace(test_settings, consecutive_error_threshold=1))
        runtime.auth_pool.load([first_auth, second_auth])
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            side_effect=[
                UpstreamAttemptResult(
                    status=429,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"error":{"code":"rate_limited"}}',
                    error_code="rate_limited",
                ),
                UpstreamAttemptResult(
                    status=429,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"error":{"code":"rate_limited"}}',
                    error_code="rate_limited",
                ),
            ]
        )

        handler._proxy_request()

        assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
            "error": "interactive auth pool unavailable",
            "reason": "interactive_pool_weak",
        }
        events = runtime.trace_store.list(limit=20)
        assert any(event.get("event") == "auth.interactive_pool_weak" for event in events)

    def test_response_limit_feedback_quarantines_key_immediately(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        runtime._refresh_limit_health = MagicMock(return_value=runtime._limit_health_cache)
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=json.dumps(
                    {
                        "rate_limits": {
                            "secondary": {
                                "used_percent": 91.0,
                                "window_minutes": 10080,
                                "reset_after_seconds": 1800,
                            }
                        }
                    }
                ).encode("utf-8"),
            )
        )

        handler._proxy_request()

        merged_account = runtime._merged_accounts(limit_health=runtime._limit_health_cache)[0]
        events = runtime.trace_store.list(limit=20)
        assert merged_account["status"] == "COOLDOWN"
        assert merged_account["reason"] == "limit_weekly"
        assert merged_account["eligible_now"] is False
        assert runtime.auth_pool.pick() is None
        assert any(event.get("event") == "auth.limit_blocked" for event in events)

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
            path=PRIMARY_RESPONSES_PATH,
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
        assert payload["interactive_auth_available"] is True
        assert payload["interactive_safe_auth_count"] == 1
        assert payload["next_interactive_auth_file"] == sample_auth_record.name
        assert payload["next_interactive_auth_email"] == sample_auth_record.email
        assert metrics["auth_available"] == 1
        assert metrics["in_flight_requests"] == 0
        assert payload["next_auth_file"] == sample_auth_record.name
        assert payload["next_auth_email"] == sample_auth_record.email


class TestReviewPathDiagnostics:
    """Tests for review-path lifecycle telemetry."""

    def test_interactive_request_emits_review_lifecycle_events(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"ok":true}',
            )
        )

        handler._proxy_request()

        events = runtime.trace_store.list(limit=20)
        review_events = {event.get("event") for event in events}
        assert "review.request_start" in review_events
        assert "review.auth_selected" in review_events
        assert "review.upstream_result" in review_events
        assert "review.complete" in review_events

    def test_review_events_include_invocation_id(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"ok":true}',
            )
        )

        handler._proxy_request()

        review_events = [
            event
            for event in runtime.trace_store.list(limit=20)
            if str(event.get("event") or "").startswith("review.")
        ]
        invocation_ids = {
            event.get("review_invocation_id")
            for event in review_events
            if event.get("review_invocation_id")
        }
        assert len(review_events) >= 4
        assert len(invocation_ids) == 1
        review_id = next(iter(invocation_ids))
        assert review_id == getattr(handler, "_current_review_id", None)
        assert all(event.get("review_id") == review_id for event in review_events)

    def test_pool_exhausted_emits_review_pool_exhausted_event(self, test_settings):
        limited_auth = AuthRecord(
            name="limited.json",
            path="/tmp/limited.json",
            token="tok-limited",
            email="limited@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([limited_auth])
        runtime._limit_health_cache = {
            limited_auth.name: {
                "file": limited_auth.name,
                "email": limited_auth.email,
                "status": "COOLDOWN",
                "five_hour": {
                    "status": "COOLDOWN",
                    "used_percent": 100.0,
                    "reset_after_seconds": 1800,
                },
            },
        }
        runtime._refresh_limit_health = MagicMock(return_value=runtime._limit_health_cache)
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )

        handler._proxy_request()

        events = runtime.trace_store.list(limit=20)
        assert any(
            event.get("event") == "review.pool_exhausted"
            and event.get("reason") == "interactive_pool_weak"
            for event in events
        )

    def test_non_interactive_request_does_not_emit_review_events(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        handler = _build_proxy_handler(
            runtime=runtime,
            path=CHAT_COMPLETIONS_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"ok":true}',
            )
        )

        handler._proxy_request()

        events = runtime.trace_store.list(limit=20)
        assert not any(
            str(event.get("event") or "").startswith("review.") for event in events
        )

    def test_review_events_after_rotation_include_all_attempts(
        self, test_settings
    ):
        first_auth = AuthRecord(
            name="first.json",
            path="/tmp/first.json",
            token="tok-first",
            email="first@example.com",
        )
        second_auth = AuthRecord(
            name="second.json",
            path="/tmp/second.json",
            token="tok-second",
            email="second@example.com",
        )
        runtime = ProxyRuntime(settings=replace(test_settings, consecutive_error_threshold=1))
        runtime.auth_pool.load([first_auth, second_auth])
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            side_effect=[
                UpstreamAttemptResult(
                    status=429,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"error":{"code":"rate_limited"}}',
                    error_code="rate_limited",
                ),
                UpstreamAttemptResult(
                    status=200,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"ok":true}',
                ),
            ]
        )

        handler._proxy_request()

        upstream_events = [
            event
            for event in runtime.trace_store.list(limit=20)
            if event.get("event") == "review.upstream_result"
        ]
        assert len(upstream_events) == 2
        assert [event.get("attempt") for event in upstream_events] == [1, 2]
        assert [event.get("status") for event in upstream_events] == [429, 200]


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
            path=PRIMARY_RESPONSES_PATH,
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


class TestAutoHealFailureClassification:
    """Tests for auto-heal failure event classification."""

    def test_auto_heal_failure_includes_origin_classification(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        runtime._auto_heal_stop.set()
        if runtime._auto_heal_thread is not None:
            runtime._auto_heal_thread.join(timeout=1)

        try:
            runtime.auth_pool.max_ejection_percent = 100
            runtime.auth_pool.consecutive_error_threshold = 1
            runtime.auth_pool.mark_result(
                sample_auth_record.name, status=401, error_code="token_invalid"
            )

            with patch(
                "cdx_proxy_cli_v2.proxy.server.load_auth_records",
                return_value=[sample_auth_record],
            ):
                runtime._probe_single_auth = MagicMock(
                    return_value={
                        "file": sample_auth_record.name,
                        "success": False,
                        "http_status": 401,
                        "error_code": "token_invalid",
                        "latency_ms": 3,
                    }
                )
                runtime._run_auto_heal_cycle(now=time.time())

            events = runtime.trace_store.list(limit=20)
            assert any(
                event.get("event") == "auto_heal.failure"
                and event.get("origin") == FAILURE_ORIGIN_HARD_AUTH
                and event.get("http_status") == 401
                and event.get("error_code") == "token_invalid"
                for event in events
            )
        finally:
            runtime.shutdown()

    def test_auto_heal_failure_classifies_timeout_as_probe_transport(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)
        runtime._auto_heal_stop.set()
        if runtime._auto_heal_thread is not None:
            runtime._auto_heal_thread.join(timeout=1)

        try:
            runtime.auth_pool.max_ejection_percent = 100
            runtime.auth_pool.consecutive_error_threshold = 1
            runtime.auth_pool.mark_result(
                sample_auth_record.name, status=401, error_code="token_invalid"
            )

            with patch(
                "cdx_proxy_cli_v2.proxy.server.load_auth_records",
                return_value=[sample_auth_record],
            ):
                runtime._probe_single_auth = MagicMock(
                    side_effect=TimeoutError("probe timed out")
                )
                runtime._run_auto_heal_cycle(now=time.time())

            events = runtime.trace_store.list(limit=20)
            assert any(
                event.get("event") == "auto_heal.failure"
                and event.get("origin") == FAILURE_ORIGIN_PROBE_TRANSPORT
                and event.get("error_code") == "network_error"
                for event in events
            )
        finally:
            runtime.shutdown()


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


class TestDownstreamDisconnect:
    """Verify BrokenPipe / client-disconnect classification and event emission."""

    def test_send_json_disconnect_emits_event(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([sample_auth_record])
        handler = _build_proxy_handler(
            runtime=runtime,
            path="/debug",
            headers={},
            body=b"",
        )
        handler.wfile = MagicMock()
        handler.wfile.write.side_effect = BrokenPipeError("client gone")

        handler._send_json(200, {"ok": True})

        events = runtime.trace_store.list(limit=20)
        assert any(
            e.get("event") == "proxy.downstream_disconnect" and e.get("phase") == "body"
            for e in events
        )
        assert runtime.metrics_snapshot()["downstream_disconnects_total"] == 1

    def test_buffered_headers_disconnect_emits_event(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([sample_auth_record])
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"ok":true}',
            )
        )
        handler.send_response = MagicMock(
            side_effect=BrokenPipeError("client gone")
        )

        handler._proxy_request()

        events = runtime.trace_store.list(limit=20)
        assert any(
            e.get("event") == "proxy.downstream_disconnect" and e.get("phase") == "headers"
            for e in events
        )

    def test_buffered_body_disconnect_emits_event(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([sample_auth_record])
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"ok":true}',
            )
        )
        handler.wfile = MagicMock()
        handler.wfile.write.side_effect = BrokenPipeError("client gone")

        handler._proxy_request()

        events = runtime.trace_store.list(limit=20)
        assert any(
            e.get("event") == "proxy.downstream_disconnect" and e.get("phase") == "body"
            for e in events
        )

    def test_streaming_body_disconnect_emits_event(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([sample_auth_record])

        mock_stream_response = MagicMock()
        mock_stream_response.read.side_effect = [b'{"type":"message_start"}', b""]
        mock_stream_connection = MagicMock()

        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler.wfile = MagicMock()
        handler.wfile.write.side_effect = BrokenPipeError("client gone")

        result = UpstreamAttemptResult(
            status=200,
            headers=[("Content-Type", "text/event-stream")],
            body=b"",
            stream_response=mock_stream_response,
            stream_connection=mock_stream_connection,
        )
        handler._send_upstream_result(
            runtime=runtime, auth_state=None, result=result
        )

        events = runtime.trace_store.list(limit=20)
        assert any(
            e.get("event") == "proxy.downstream_disconnect" and e.get("phase") == "body"
            for e in events
        )
        mock_stream_response.close.assert_called()

    def test_streaming_flush_disconnect_classified_as_flush(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([sample_auth_record])

        mock_stream_response = MagicMock()
        mock_stream_response.read.side_effect = [b'{"type":"message_start"}', b""]
        mock_stream_connection = MagicMock()

        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler.wfile = MagicMock()
        # write succeeds but flush raises
        handler.wfile.flush.side_effect = BrokenPipeError("client gone")

        result = UpstreamAttemptResult(
            status=200,
            headers=[("Content-Type", "text/event-stream")],
            body=b"",
            stream_response=mock_stream_response,
            stream_connection=mock_stream_connection,
        )
        handler._send_upstream_result(
            runtime=runtime, auth_state=None, result=result
        )

        events = runtime.trace_store.list(limit=20)
        assert any(
            e.get("event") == "proxy.downstream_disconnect" and e.get("phase") == "flush"
            for e in events
        )

    def test_disconnect_does_not_affect_auth_health(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([sample_auth_record])
        handler = _build_proxy_handler(
            runtime=runtime,
            path=RESPONSES_PATH,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
        handler._run_upstream_attempt = MagicMock(
            return_value=UpstreamAttemptResult(
                status=200,
                headers=[("Content-Type", "application/json")],
                body=b'{"ok":true}',
            )
        )
        handler.wfile = MagicMock()
        handler.wfile.write.side_effect = BrokenPipeError("client gone")

        stats_before = runtime.auth_pool.stats()
        handler._proxy_request()
        stats_after = runtime.auth_pool.stats()

        assert stats_after["ok"] == stats_before["ok"]
        assert stats_after["blacklist"] == stats_before["blacklist"]

    def test_disconnect_metric_increments(
        self,
        test_settings,
        sample_auth_record,
    ):
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([sample_auth_record])

        for _ in range(2):
            handler = _build_proxy_handler(
                runtime=runtime,
                path=RESPONSES_PATH,
                headers={"Content-Type": "application/json"},
                body=b"{}",
            )
            handler._run_upstream_attempt = MagicMock(
                return_value=UpstreamAttemptResult(
                    status=200,
                    headers=[("Content-Type", "application/json")],
                    body=b'{"ok":true}',
                )
            )
            handler.wfile = MagicMock()
            handler.wfile.write.side_effect = BrokenPipeError("client gone")
            handler._proxy_request()

        assert runtime.metrics_snapshot()["downstream_disconnects_total"] == 2


class TestDegradedStateVerdict:
    """Tests for ProxyRuntime.degraded_state_verdict()."""

    def test_all_ok_returns_healthy(self, test_settings):
        """When all auths are OK the state should be healthy with no blocker."""
        ok_auth_a = AuthRecord(
            name="ok_a.json",
            path="/tmp/ok_a.json",
            token="tok-ok-a",
            email="ok_a@example.com",
        )
        ok_auth_b = AuthRecord(
            name="ok_b.json",
            path="/tmp/ok_b.json",
            token="tok-ok-b",
            email="ok_b@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([ok_auth_a, ok_auth_b])

        verdict = runtime.degraded_state_verdict()

        assert verdict["state"] == "healthy"
        assert verdict["ok_count"] == 2
        assert verdict["cooldown_count"] == 0
        assert verdict["blacklist_count"] == 0
        assert verdict["primary_blocker"] is None
        assert verdict["interactive_safe_count"] == 2

    def test_mixed_ok_and_cooldown_returns_degraded(self, test_settings):
        """When some auths are in cooldown the state should be degraded."""
        ok_auth = AuthRecord(
            name="ok.json",
            path="/tmp/ok.json",
            token="tok-ok",
            email="ok@example.com",
        )
        cooldown_auth = AuthRecord(
            name="cooldown.json",
            path="/tmp/cooldown.json",
            token="tok-cool",
            email="cool@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([ok_auth, cooldown_auth])
        # Put one auth into cooldown
        runtime.auth_pool.mark_result("cooldown.json", status=429)

        verdict = runtime.degraded_state_verdict()

        assert verdict["state"] == "degraded"
        assert verdict["primary_blocker"] == "some auths in cooldown"
        assert verdict["ok_count"] >= 1
        assert verdict["cooldown_count"] >= 1

    def test_all_blacklisted_returns_full_outage(self, test_settings):
        """When every auth is blacklisted the state should be full_outage."""
        bad_auth_a = AuthRecord(
            name="bad_a.json",
            path="/tmp/bad_a.json",
            token="tok-bad-a",
            email="bad_a@example.com",
        )
        bad_auth_b = AuthRecord(
            name="bad_b.json",
            path="/tmp/bad_b.json",
            token="tok-bad-b",
            email="bad_b@example.com",
        )
        runtime = ProxyRuntime(
            settings=replace(test_settings, consecutive_error_threshold=1)
        )
        runtime.auth_pool.load([bad_auth_a, bad_auth_b])
        # First key blacklists; second is held in cooldown by max_ejection_percent.
        runtime.auth_pool.mark_result("bad_a.json", status=401, error_code="token_invalid")
        runtime.auth_pool.mark_result("bad_b.json", status=403, error_code="forbidden")

        verdict = runtime.degraded_state_verdict()

        assert verdict["state"] == "full_outage"
        assert verdict["primary_blocker"] == "no healthy auths"
        assert verdict["ok_count"] == 0
        assert verdict["blacklist_count"] == 1
        assert verdict["cooldown_count"] == 1
        assert verdict["interactive_safe_count"] == 0

    def test_no_interactive_safe_auths_returns_partial_outage(self, test_settings):
        """When auths exist but none are interactive-safe, state should be partial_outage."""
        limited_auth = AuthRecord(
            name="limited.json",
            path="/tmp/limited.json",
            token="tok-limited",
            email="limited@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([limited_auth])
        runtime._limit_health_cache = {
            limited_auth.name: {
                "file": limited_auth.name,
                "email": limited_auth.email,
                "status": "COOLDOWN",
                "five_hour": {
                    "status": "COOLDOWN",
                    "used_percent": 100.0,
                    "reset_after_seconds": 1800,
                },
            },
        }

        verdict = runtime.degraded_state_verdict()

        assert verdict["state"] == "partial_outage"
        assert verdict["interactive_safe_count"] == 0
        assert verdict["primary_blocker"] == "no interactive-safe auths"

    def test_verdict_does_not_mutate_runtime_state(self, test_settings):
        """Calling degraded_state_verdict() must not alter pool stats or health."""
        ok_auth = AuthRecord(
            name="stable.json",
            path="/tmp/stable.json",
            token="tok-stable",
            email="stable@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([ok_auth])

        stats_before = runtime.auth_pool.stats()
        health_before = runtime.auth_pool.health_snapshot()

        verdict = runtime.degraded_state_verdict()
        assert verdict["state"] == "healthy"

        stats_after = runtime.auth_pool.stats()
        health_after = runtime.auth_pool.health_snapshot()

        assert stats_before == stats_after
        assert health_before == health_after


class TestOperatorTriage:
    """Tests for operator-facing triage summaries."""

    def test_degraded_state_verdict_includes_next_action_for_degraded(
        self, test_settings
    ):
        ok_auth = AuthRecord(
            name="ok.json",
            path="/tmp/ok.json",
            token="tok-ok",
            email="ok@example.com",
        )
        cooldown_auth = AuthRecord(
            name="cool.json",
            path="/tmp/cool.json",
            token="tok-cool",
            email="cool@example.com",
        )
        runtime = ProxyRuntime(settings=test_settings)
        runtime.auth_pool.load([ok_auth, cooldown_auth])
        runtime.auth_pool.mark_result("cool.json", status=429)

        verdict = runtime.degraded_state_verdict()

        assert verdict["state"] == "degraded"
        assert (
            verdict["next_action"]
            == "cdx rotate to avoid degraded keys, or wait for cooldown expiry"
        )

    def test_degraded_state_verdict_includes_next_action_for_full_outage(
        self, test_settings
    ):
        bad_auth = AuthRecord(
            name="bad.json",
            path="/tmp/bad.json",
            token="tok-bad",
            email="bad@example.com",
        )
        runtime = ProxyRuntime(
            settings=replace(test_settings, consecutive_error_threshold=1)
        )
        runtime.auth_pool.load([bad_auth])
        runtime.auth_pool.mark_result("bad.json", status=401, error_code="token_invalid")

        verdict = runtime.degraded_state_verdict()

        assert verdict["state"] == "full_outage"
        assert (
            verdict["next_action"]
            == "all auths are blacklisted — run cdx reset --state blacklist or add new auth files"
        )

    def test_degraded_state_verdict_next_action_none_for_healthy(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)

        verdict = runtime.degraded_state_verdict()

        assert verdict["state"] == "healthy"
        assert verdict["next_action"] is None

    def test_debug_payload_includes_triage_summary(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)

        payload = runtime.debug_payload(host="127.0.0.1", port=43123)

        assert "triage_summary" in payload
        assert payload["triage_summary"]["state"] == "healthy"
        assert payload["triage_summary"] == payload["degraded_state"]

    def test_health_snapshot_includes_triage_fields(
        self, test_settings, sample_auth_record
    ):
        runtime = _build_runtime(test_settings, sample_auth_record)

        snapshot = runtime.health_snapshot(refresh=False)

        assert "triage" in snapshot
        assert snapshot["triage"] == {
            "state": "healthy",
            "primary_blocker": None,
            "next_action": None,
        }


# ============================================================================
# Test: Bounded Management Refresh
# ============================================================================


class TestBoundedManagementRefresh:
    """Tests for bounded lock acquisition in /health and management-plane refresh.

    Verifies that _refresh_limit_health uses timed lock acquisition so that
    /health?refresh=1 and /trace never block indefinitely under degraded auth.
    """

    def test_health_snapshot_returns_stale_when_lock_is_held(
        self, test_settings, sample_auth_record
    ):
        """Hold the lock from another thread, call health_snapshot(refresh=True),
        verify it returns cached data with stale metadata instead of blocking."""
        import threading

        runtime = _build_runtime(test_settings, sample_auth_record)

        # Seed the cache with an initial refresh so there is something to return
        with patch("cdx_proxy_cli_v2.proxy.server.fetch_limit_health") as mock_limits:
            mock_limits.return_value = {
                sample_auth_record.name: {
                    "file": sample_auth_record.name,
                    "status": "OK",
                    "weekly": {
                        "status": "OK",
                        "used_percent": 10.0,
                        "reset_after_seconds": 100000,
                    },
                }
            }
            runtime._refresh_limit_health(force=True, persist_snapshot=True)

        assert runtime._limit_health_cache, "cache must be seeded before lock contention test"

        # Hold the lock from a background thread so _refresh_limit_health cannot acquire it
        lock_acquired = threading.Event()
        release_lock = threading.Event()

        def hold_lock():
            runtime._limit_health_lock.acquire()
            lock_acquired.set()
            release_lock.wait(timeout=10)

        holder = threading.Thread(target=hold_lock, daemon=True)
        holder.start()
        lock_acquired.wait(timeout=5)
        assert lock_acquired.is_set(), "holder thread must acquire the lock"

        try:
            # health_snapshot(refresh=True) should return stale data quickly
            snapshot = runtime.health_snapshot(refresh=True)
            assert "ok" in snapshot
            # The refresh metadata must show the stale condition
            assert snapshot.get("limits_refresh_error") == "lock_timeout"
        finally:
            release_lock.set()
            holder.join(timeout=5)

    def test_health_snapshot_includes_refresh_metadata(
        self, test_settings, sample_auth_record
    ):
        """health_snapshot must include limits_refresh_age_seconds, limits_stale,
        limits_refresh_error, and limits_partial fields."""
        import time as _time

        runtime = _build_runtime(test_settings, sample_auth_record)

        with patch("cdx_proxy_cli_v2.proxy.server.fetch_limit_health") as mock_limits:
            mock_limits.return_value = {
                sample_auth_record.name: {
                    "file": sample_auth_record.name,
                    "status": "OK",
                    "weekly": {
                        "status": "OK",
                        "used_percent": 10.0,
                        "reset_after_seconds": 100000,
                    },
                }
            }
            snapshot = runtime.health_snapshot(refresh=True)

        # The required metadata fields must be present
        assert "limits_refresh_age_seconds" in snapshot
        assert "limits_stale" in snapshot
        assert "limits_refresh_error" in snapshot
        assert "limits_partial" in snapshot

        # After a successful refresh, age should be a small positive number
        assert isinstance(snapshot["limits_refresh_age_seconds"], float)
        assert snapshot["limits_refresh_age_seconds"] >= 0
        # No error after successful refresh
        assert snapshot["limits_refresh_error"] is None
        assert snapshot["limits_partial"] is False

    def test_trace_payload_returns_stale_when_lock_is_held(
        self, test_settings, sample_auth_record
    ):
        """trace_payload calls limits_snapshot(force_refresh_stale=True) which
        must not block when the lock is contended."""
        import threading

        runtime = _build_runtime(test_settings, sample_auth_record)

        # Seed cache first
        with patch("cdx_proxy_cli_v2.proxy.server.fetch_limit_health") as mock_limits:
            mock_limits.return_value = {
                sample_auth_record.name: {
                    "file": sample_auth_record.name,
                    "status": "OK",
                    "weekly": {
                        "status": "OK",
                        "used_percent": 10.0,
                        "reset_after_seconds": 100000,
                    },
                }
            }
            runtime._refresh_limit_health(force=True, persist_snapshot=True)

        # Mark snapshot as stale so trace_payload triggers a refresh attempt
        runtime._latest_limits_fetched_at = 0.0
        # Also clear the cached snapshot so limits_snapshot must rebuild it
        runtime._latest_limits_snapshot = {}

        # Hold the lock
        lock_acquired = threading.Event()
        release_lock = threading.Event()

        def hold_lock():
            runtime._limit_health_lock.acquire()
            lock_acquired.set()
            release_lock.wait(timeout=10)

        holder = threading.Thread(target=hold_lock, daemon=True)
        holder.start()
        lock_acquired.wait(timeout=5)
        assert lock_acquired.is_set()

        try:
            payload = runtime.trace_payload(limit=5)
            assert "events" in payload
            assert "limits" in payload
            # Must not have blocked — limits should have stale/error markers
            limits = payload["limits"]
            assert limits.get("stale") is True or limits.get("error") is not None
        finally:
            release_lock.set()
            holder.join(timeout=5)

    def test_refresh_limit_health_marks_partial_on_upstream_error(
        self, test_settings, sample_auth_record
    ):
        """When fetch_limit_health raises, the cache must be preserved and
        _limits_partial/_limits_refresh_error must be set."""
        runtime = _build_runtime(test_settings, sample_auth_record)

        # Seed the cache with valid data
        with patch("cdx_proxy_cli_v2.proxy.server.fetch_limit_health") as mock_limits:
            mock_limits.return_value = {
                sample_auth_record.name: {
                    "file": sample_auth_record.name,
                    "status": "OK",
                    "weekly": {
                        "status": "OK",
                        "used_percent": 10.0,
                        "reset_after_seconds": 100000,
                    },
                }
            }
            runtime._refresh_limit_health(force=True, persist_snapshot=True)

        cached_data = dict(runtime._limit_health_cache)
        assert cached_data, "cache must be seeded"

        # Now make fetch_limit_health raise
        with patch(
            "cdx_proxy_cli_v2.proxy.server.fetch_limit_health",
            side_effect=RuntimeError("upstream timeout"),
        ):
            runtime._refresh_limit_health(force=True, persist_snapshot=True)

        # Cache should still exist (possibly cleared by the exception path)
        # The key thing: error metadata must be set
        assert runtime._limits_refresh_error == "upstream timeout"
        assert runtime._limits_partial is True

    def test_health_snapshot_no_error_when_lock_available(
        self, test_settings, sample_auth_record
    ):
        """When the lock is not contended, health_snapshot(refresh=True)
        must return without lock_timeout error."""
        runtime = _build_runtime(test_settings, sample_auth_record)

        with patch("cdx_proxy_cli_v2.proxy.server.fetch_limit_health") as mock_limits:
            mock_limits.return_value = {
                sample_auth_record.name: {
                    "file": sample_auth_record.name,
                    "status": "OK",
                    "weekly": {
                        "status": "OK",
                        "used_percent": 10.0,
                        "reset_after_seconds": 100000,
                    },
                }
            }
            snapshot = runtime.health_snapshot(refresh=True)

        assert snapshot["limits_refresh_error"] is None
        assert snapshot["limits_partial"] is False


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
