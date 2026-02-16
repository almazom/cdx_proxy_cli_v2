"""Test that EventLogger sanitizes sensitive fields."""
from __future__ import annotations

import json
import tempfile

from cdx_proxy_cli_v2.observability.event_log import (
    EventLogger,
    _is_sensitive_field,
    SENSITIVE_FIELD_NAMES,
)


class TestSensitiveFieldDetection:
    """Tests for _is_sensitive_field function."""

    def test_exact_match_sensitive_fields(self):
        """Exact matches should be detected as sensitive."""
        for field in SENSITIVE_FIELD_NAMES:
            assert _is_sensitive_field(field), f"{field} should be sensitive"
            assert _is_sensitive_field(field.upper()), f"{field.upper()} should be sensitive"
            assert _is_sensitive_field(field.title()), f"{field.title()} should be sensitive"

    def test_compound_sensitive_fields(self):
        """Compound names containing sensitive words should be detected."""
        sensitive_compounds = [
            "user_token",
            "api_secret_key",
            "my_password",
            "access_token_v2",
            "private_key_data",
        ]
        for field in sensitive_compounds:
            assert _is_sensitive_field(field), f"{field} should be sensitive"

    def test_safe_fields_not_flagged(self):
        """Normal field names should not be flagged as sensitive."""
        safe_fields = [
            "email",
            "file",
            "status",
            "count",
            "latency_ms",
            "request_id",
            "method",
            "path",
            "account_id",
            "used",
            "errors",
        ]
        for field in safe_fields:
            assert not _is_sensitive_field(field), f"{field} should NOT be sensitive"


class TestEventLoggerSanitization:
    """Tests for EventLogger field sanitization."""

    def test_token_is_redacted(self):
        """Token field should be redacted in log output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(tmpdir)
            logger.write(
                level="INFO",
                event="test",
                message="test",
                token="secret-token-12345",
            )

            log_content = logger.path.read_text()
            assert "secret-token-12345" not in log_content
            assert "[REDACTED]" in log_content

    def test_access_token_is_redacted(self):
        """access_token field should be redacted in log output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(tmpdir)
            logger.write(
                level="INFO",
                event="test",
                message="test",
                access_token="secret-access-token",
            )

            log_content = logger.path.read_text()
            assert "secret-access-token" not in log_content

    def test_api_key_is_redacted(self):
        """api_key field should be redacted in log output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(tmpdir)
            logger.write(
                level="INFO",
                event="test",
                message="test",
                api_key="sk-12345abcdef",
            )

            log_content = logger.path.read_text()
            assert "sk-12345abcdef" not in log_content

    def test_password_is_redacted(self):
        """password field should be redacted in log output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(tmpdir)
            logger.write(
                level="INFO",
                event="test",
                message="test",
                password="my-secret-password",
            )

            log_content = logger.path.read_text()
            assert "my-secret-password" not in log_content
            assert "[REDACTED]" in log_content

    def test_normal_fields_preserved(self):
        """Non-sensitive fields should be preserved in log output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(tmpdir)
            logger.write(
                level="INFO",
                event="proxy.request",
                message="request completed",
                request_id="abc123",
                status=200,
                latency_ms=150,
                email="user@example.com",
            )

            log_content = logger.path.read_text()
            record = json.loads(log_content.strip())

            assert record["request_id"] == "abc123"
            assert record["status"] == 200
            assert record["latency_ms"] == 150
            assert record["email"] == "user@example.com"

    def test_mixed_sensitive_and_normal_fields(self):
        """Should handle mix of sensitive and normal fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = EventLogger(tmpdir)
            logger.write(
                level="INFO",
                event="test",
                message="test",
                token="secret-token",
                email="user@example.com",
                api_key="secret-key",
                status=200,
            )

            log_content = logger.path.read_text()
            record = json.loads(log_content.strip())

            assert record["token"] == "[REDACTED]"
            assert record["api_key"] == "[REDACTED]"
            assert record["email"] == "user@example.com"
            assert record["status"] == 200
