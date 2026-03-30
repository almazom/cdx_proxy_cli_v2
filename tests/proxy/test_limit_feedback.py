from __future__ import annotations

import json

from cdx_proxy_cli_v2.proxy.limit_feedback import (
    merge_limit_feedback,
    parse_limit_feedback,
)


def test_parse_limit_feedback_from_headers(monkeypatch) -> None:
    monkeypatch.setattr("cdx_proxy_cli_v2.proxy.limit_feedback.time.time", lambda: 1000.0)

    feedback = parse_limit_feedback(
        headers=[
            ("x-codex-primary-used-percent", "72"),
            ("x-codex-primary-window-minutes", "300"),
            ("x-codex-primary-reset-at", "1300"),
            ("x-codex-secondary-used-percent", "91"),
            ("x-codex-secondary-window-minutes", "10080"),
            ("x-codex-secondary-reset-at", "4600"),
        ],
        body=b"",
    )

    assert feedback is not None
    assert feedback["status"] == "COOLDOWN"
    assert feedback["five_hour"]["status"] == "WARN"
    assert feedback["five_hour"]["reset_after_seconds"] == 300
    assert feedback["weekly"]["status"] == "COOLDOWN"
    assert feedback["weekly"]["reset_after_seconds"] == 3600


def test_parse_limit_feedback_from_body_rate_limits_payload() -> None:
    feedback = parse_limit_feedback(
        headers=[],
        body=json.dumps(
            {
                "rate_limits": {
                    "primary": {
                        "used_percent": 74.0,
                        "window_minutes": 300,
                        "reset_after_seconds": 900,
                    },
                    "secondary": {
                        "used_percent": 88.0,
                        "window_minutes": 10080,
                        "reset_after_seconds": 7200,
                    },
                }
            }
        ).encode("utf-8"),
    )

    assert feedback is not None
    assert feedback["status"] == "WARN"
    assert feedback["five_hour"]["used_percent"] == 74.0
    assert feedback["weekly"]["used_percent"] == 88.0


def test_merge_limit_feedback_preserves_existing_windows() -> None:
    merged = merge_limit_feedback(
        existing={
            "file": "a.json",
            "email": "a@example.com",
            "status": "OK",
            "weekly": {
                "status": "OK",
                "used_percent": 22.0,
                "reset_after_seconds": 5000,
            },
        },
        feedback={
            "status": "WARN",
            "five_hour": {
                "status": "WARN",
                "used_percent": 76.0,
                "reset_after_seconds": 1200,
            },
        },
        auth_name="a.json",
        auth_email="a@example.com",
    )

    assert merged["status"] == "WARN"
    assert merged["five_hour"]["used_percent"] == 76.0
    assert merged["weekly"]["used_percent"] == 22.0
