from __future__ import annotations

from cdx_proxy_cli_v2.auth.eligibility import limit_block_details
from cdx_proxy_cli_v2.health_snapshot import window_summary


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
