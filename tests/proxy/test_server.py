"""Comprehensive tests for proxy server module."""
from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import RoundRobinAuthPool
from cdx_proxy_cli_v2.config.settings import Settings
from cdx_proxy_cli_v2.proxy.server import _extract_error_code


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
    pool = RoundRobinAuthPool()
    pool.load([sample_auth_record])
    return pool


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
        assert trace_route("/responses") == "request"
        assert trace_route("/codex/responses") == "request"

    def test_trace_route_compact(self):
        """Paths ending in /compact should be classified as 'compact'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route
        assert trace_route("/responses/compact") == "compact"
        assert trace_route("/responses/compact?x=1") == "compact"

    def test_trace_route_other(self):
        """Other paths should be classified as 'other'."""
        from cdx_proxy_cli_v2.proxy.rules import trace_route
        assert trace_route("/health") == "other"
        assert trace_route("/debug") == "other"
        assert trace_route("/v1/models") == "other"


# ============================================================================
# Test: Path Rewriting
# ============================================================================

class TestPathRewriting:
    """Tests for request path rewriting."""

    def test_rewrite_chatgpt_responses_paths(self):
        """ChatGPT responses paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path
        assert rewrite_request_path(
            req_path="/responses",
            upstream_host="chatgpt.com",
            upstream_base_path="/backend-api",
        ) == "/codex/responses"

    def test_rewrite_chatgpt_v1_responses_paths(self):
        """ChatGPT v1/responses paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path
        assert rewrite_request_path(
            req_path="/v1/responses",
            upstream_host="chatgpt.com",
            upstream_base_path="/backend-api",
        ) == "/codex/responses"

    def test_rewrite_compact_paths(self):
        """Compact paths should be rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path
        assert rewrite_request_path(
            req_path="/v1/responses/compact",
            upstream_host="chat.openai.com",
            upstream_base_path="/backend-api",
        ) == "/codex/responses/compact"

    def test_no_rewrite_for_other_upstreams(self):
        """Other upstreams should not have paths rewritten."""
        from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path
        assert rewrite_request_path(
            req_path="/responses",
            upstream_host="api.openai.com",
            upstream_base_path="/v1",
        ) == "/responses"


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
        from cdx_proxy_cli_v2.proxy.rules import drop_header_case_insensitive
        drop_header_case_insensitive(headers, "content-type")
        assert "Content-Type" not in headers
        assert "content-length" in headers


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
        mock_auth_pool.mark_result("test_auth.json", status=401, error_code="token_invalid")
        
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


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
