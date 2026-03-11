"""Test that tokens are never exposed in API responses."""

from __future__ import annotations

from unittest.mock import patch

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.health_snapshot import collective_health_snapshot
from cdx_proxy_cli_v2.observability.collective_dashboard import build_collective_payload


def test_health_snapshot_no_token_in_response():
    """Verify collective_health_snapshot never includes access_token."""
    mock_auth = AuthRecord(
        name="test.json",
        path="/tmp/test.json",
        token="secret-token-12345",
        email="test@example.com",
        account_id="acc-123",
    )

    with patch(
        "cdx_proxy_cli_v2.health_snapshot.load_auth_records", return_value=[mock_auth]
    ):
        with patch("cdx_proxy_cli_v2.health_snapshot.fetch_usage") as mock_fetch:
            mock_fetch.return_value = {"rate_limit": {}}

            result = collective_health_snapshot(
                auths_dir="/tmp",
                base_url="https://chatgpt.com/backend-api",
                warn_at=70,
                cooldown_at=90,
                timeout=5,
                only="both",
            )

            for account in result.get("accounts", []):
                assert "access_token" not in account, (
                    f"access_token should not be in response for {account.get('file')}"
                )
                assert "token" not in account, (
                    f"token should not be in response for {account.get('file')}"
                )


def test_build_collective_payload_no_token_in_output():
    """Verify build_collective_payload never outputs access_token."""

    mock_snapshot = {
        "accounts": [
            {
                "file": "test.json",
                "email": "test@example.com",
                "account_id": "acc-123",
                "status": "OK",
            }
        ]
    }

    with patch(
        "cdx_proxy_cli_v2.observability.collective_dashboard.collective_health_snapshot",
        return_value=mock_snapshot,
    ):
        result = build_collective_payload(
            auths_dir="/tmp",
            base_url="https://chatgpt.com/backend-api",
            warn_at=70,
            cooldown_at=90,
            timeout=5,
            only="both",
        )

        for account in result.get("accounts", []):
            assert "access_token" not in account, (
                f"access_token should not be in output for {account.get('file')}"
            )
            assert "token" not in account, (
                f"token should not be in output for {account.get('file')}"
            )
