from __future__ import annotations

import json

from cdx_proxy_cli_v2.observability.limits_history import (
    append_limits_history,
    latest_limits_path,
    limits_history_path,
    read_latest_limits_snapshot,
    write_latest_limits_snapshot,
)


def test_limits_snapshot_round_trip_sanitizes_sensitive_fields(tmp_path) -> None:
    payload = {
        "fetched_at": 123.0,
        "stale": False,
        "accounts": [
            {
                "file": "a.json",
                "email": "a@example.com",
                "status": "OK",
                "token": "secret-token",
                "five_hour": {"used_percent": 40.0, "reset_after_seconds": 600},
            }
        ],
    }

    write_latest_limits_snapshot(str(tmp_path), payload)
    snapshot = read_latest_limits_snapshot(str(tmp_path))

    assert snapshot["accounts"][0]["token"] == "[REDACTED]"
    assert "secret-token" not in latest_limits_path(str(tmp_path)).read_text()


def test_limits_history_appends_one_record_per_account(tmp_path) -> None:
    payload = {
        "fetched_at": 456.0,
        "accounts": [
            {
                "file": "a.json",
                "email": "a@example.com",
                "status": "WARN",
                "reason": "limit_5h_guardrail",
                "reason_origin": "limit_guardrail",
                "five_hour": {"used_percent": 91.0, "reset_after_seconds": 120},
                "weekly": {"used_percent": 20.0, "reset_after_seconds": 7200},
            },
            {
                "file": "b.json",
                "email": "b@example.com",
                "status": "OK",
            },
        ],
    }

    append_limits_history(str(tmp_path), payload)

    lines = limits_history_path(str(tmp_path)).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["file"] == "a.json"
    assert second["file"] == "b.json"
    assert first["reason_origin"] == "limit_guardrail"
