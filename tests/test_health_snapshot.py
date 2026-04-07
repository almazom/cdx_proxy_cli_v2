from __future__ import annotations

from cdx_proxy_cli_v2.auth.eligibility import (
    DEFAULT_LIMIT_RECHECK_SECONDS,
    credits_block_details,
    limit_block_details,
    merged_account_state,
)
from cdx_proxy_cli_v2.health_snapshot import credits_summary, window_summary


def test_global_limit_flag_does_not_mark_unrelated_window_cooldown() -> None:
    five_hour = window_summary(
        {"used_percent": 50.0, "reset_after_seconds": 18_000},
        limit_reached=True,
        warn_at=70,
        cooldown_at=90,
    )
    weekly = window_summary(
        {"used_percent": 100.0, "reset_after_seconds": 600_000},
        limit_reached=True,
        warn_at=70,
        cooldown_at=90,
    )

    assert five_hour == {
        "status": "OK",
        "used_percent": 50.0,
        "reset_after_seconds": 18_000,
    }
    assert weekly == {
        "status": "COOLDOWN",
        "used_percent": 100.0,
        "reset_after_seconds": 600_000,
    }
    assert limit_block_details({"five_hour": five_hour, "weekly": weekly}, now=0.0) == {
        "reason": "limit_weekly",
        "reason_origin": "limit",
        "cooldown_seconds": 600_000,
        "until": 600_000.0,
    }


def test_limit_block_details_quarantines_cooldown_without_reset_timer() -> None:
    result = limit_block_details({"weekly": {"status": "COOLDOWN"}}, now=100.0)

    assert result == {
        "reason": "limit_weekly",
        "reason_origin": "limit",
        "cooldown_seconds": DEFAULT_LIMIT_RECHECK_SECONDS,
        "until": 100.0 + DEFAULT_LIMIT_RECHECK_SECONDS,
    }


def test_limit_block_details_quarantines_nearly_exhausted_window() -> None:
    result = limit_block_details(
        {
            "five_hour": {
                "status": "WARN",
                "used_percent": 89.5,
                "reset_after_seconds": 1800,
            }
        },
        now=50.0,
    )

    assert result == {
        "reason": "limit_5h_guardrail",
        "reason_origin": "limit_guardrail",
        "cooldown_seconds": 1800,
        "until": 1850.0,
    }


def test_credits_summary_marks_zero_balance_and_zero_messages_exhausted() -> None:
    result = credits_summary(
        {
            "has_credits": False,
            "unlimited": False,
            "balance": "0",
            "approx_local_messages": [0, 0],
            "approx_cloud_messages": [0, 0],
        }
    )

    assert result == {
        "status": "EXHAUSTED",
        "has_credits": False,
        "unlimited": False,
        "balance": 0.0,
        "approx_local_messages": [0, 0],
        "approx_cloud_messages": [0, 0],
    }


def test_credits_block_details_quarantines_exhausted_credits() -> None:
    result = credits_block_details(
        {
            "credits": {
                "status": "EXHAUSTED",
                "has_credits": False,
                "balance": 0.0,
            }
        },
        now=25.0,
    )

    assert result == {
        "reason": "credits_exhausted",
        "reason_origin": "credits",
        "cooldown_seconds": DEFAULT_LIMIT_RECHECK_SECONDS,
        "until": 25.0 + DEFAULT_LIMIT_RECHECK_SECONDS,
    }


def test_merged_account_state_fails_closed_when_limit_data_is_missing() -> None:
    result = merged_account_state(
        {"file": "a.json", "status": "OK", "eligible_now": True},
        {},
    )

    assert result["status"] == "UNKNOWN"
    assert result["eligible_now"] is False
    assert result["reason"] == "limit_unavailable"
    assert result["reason_origin"] == "limit"
    assert result["selection_known"] is False
    assert result["selection_source"] == "unknown"


def test_merged_account_state_does_not_promote_limit_only_auth_to_healthy() -> None:
    result = merged_account_state(
        {},
        {
            "file": "b.json",
            "status": "OK",
            "five_hour": {
                "status": "OK",
                "used_percent": 10.0,
                "reset_after_seconds": 300,
            },
        },
    )

    assert result["status"] == "UNKNOWN"
    assert result["eligible_now"] is False
    assert result["reason"] == "runtime_unavailable"
    assert result["reason_origin"] == "runtime"
    assert result["selection_known"] is True
    assert result["selection_source"] == "preferred"


def test_merged_account_state_marks_near_limit_key_degraded_without_blocking() -> None:
    result = merged_account_state(
        {"file": "c.json", "status": "OK", "eligible_now": True},
        {
            "file": "c.json",
            "status": "WARN",
            "five_hour": {
                "status": "WARN",
                "used_percent": 89.5,
                "reset_after_seconds": 1800,
            },
        },
        min_remaining_percent=30.0,
    )

    assert result["status"] == "WARN"
    assert result["eligible_now"] is True
    assert result["selection_known"] is True
    assert result["selection_preferred"] is False
    assert result["selection_source"] == "degraded"
    assert result["selection_remaining_percent"] == 10.5


def test_merged_account_state_blocks_exhausted_credits_even_with_ok_limits() -> None:
    result = merged_account_state(
        {"file": "a.json", "status": "OK", "eligible_now": True},
        {
            "file": "a.json",
            "status": "OK",
            "five_hour": {
                "status": "OK",
                "used_percent": 10.0,
                "reset_after_seconds": 300,
            },
            "credits": {
                "status": "EXHAUSTED",
                "has_credits": False,
                "balance": 0.0,
                "approx_local_messages": [0, 0],
                "approx_cloud_messages": [0, 0],
            },
        },
    )

    assert result["status"] == "COOLDOWN"
    assert result["eligible_now"] is False
    assert result["reason"] == "credits_exhausted"
    assert result["reason_origin"] == "credits"
    assert result["cooldown_seconds"] == DEFAULT_LIMIT_RECHECK_SECONDS
