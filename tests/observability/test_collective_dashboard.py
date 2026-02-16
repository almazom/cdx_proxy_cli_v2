from __future__ import annotations

from cdx_proxy_cli_v2.observability.collective_dashboard import (
    _window_text,
    build_collective_payload,
    format_left_percent,
)


def test_format_left_percent_known_percent() -> None:
    assert format_left_percent(25) == "75% left"


def test_format_left_percent_unknown_percent() -> None:
    assert format_left_percent(None) == "unknown left"


def test_window_text_includes_left_only() -> None:
    text = _window_text({"status": "OK", "used_percent": 50, "reset_after_seconds": 120})
    plain = text.plain
    assert "50% left" in plain
    assert "reset 2m" in plain


def test_build_collective_payload_marks_current_by_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "cdx_proxy_cli_v2.observability.collective_dashboard.collective_health_snapshot",
        lambda **_kwargs: {
            "accounts": [
                {
                    "file": "a.json",
                    "email": "target@example.com",
                    "access_token": "t-a",
                    "account_id": "acct-a",
                    "status": "OK",
                },
                {
                    "file": "b.json",
                    "email": "other@example.com",
                    "access_token": "t-b",
                    "account_id": "acct-b",
                    "status": "OK",
                },
            ]
        },
    )
    payload = build_collective_payload(
        auths_dir="~/.codex/_auths",
        base_url="https://chatgpt.com/backend-api",
        warn_at=70,
        cooldown_at=90,
        timeout=8,
        only="both",
        current_email="target@example.com",
    )
    accounts = payload["accounts"]
    assert accounts[0]["current"] is True
    assert accounts[1]["current"] is False
    assert "access_token" not in accounts[0]
    assert "account_id" not in accounts[0]


def test_build_collective_payload_marks_current_by_account_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "cdx_proxy_cli_v2.observability.collective_dashboard.collective_health_snapshot",
        lambda **_kwargs: {
            "accounts": [
                {
                    "file": "a.json",
                    "email": "a@example.com",
                    "access_token": "t-a",
                    "account_id": "acct-a",
                    "status": "OK",
                },
                {
                    "file": "b.json",
                    "email": "b@example.com",
                    "access_token": "t-b",
                    "account_id": "acct-b",
                    "status": "OK",
                },
            ]
        },
    )
    payload = build_collective_payload(
        auths_dir="~/.codex/_auths",
        base_url="https://chatgpt.com/backend-api",
        warn_at=70,
        cooldown_at=90,
        timeout=8,
        only="both",
        current_account_id="acct-b",
    )
    accounts = payload["accounts"]
    assert accounts[0]["current"] is False
    assert accounts[1]["current"] is True


def test_build_collective_payload_account_id_collision_marks_single_current(monkeypatch) -> None:
    monkeypatch.setattr(
        "cdx_proxy_cli_v2.observability.collective_dashboard.collective_health_snapshot",
        lambda **_kwargs: {
            "accounts": [
                {
                    "file": "a.json",
                    "email": "a@example.com",
                    "access_token": "t-a",
                    "account_id": "shared-acct",
                    "status": "OK",
                },
                {
                    "file": "b.json",
                    "email": "b@example.com",
                    "access_token": "t-b",
                    "account_id": "shared-acct",
                    "status": "OK",
                },
            ]
        },
    )
    payload = build_collective_payload(
        auths_dir="~/.codex/_auths",
        base_url="https://chatgpt.com/backend-api",
        warn_at=70,
        cooldown_at=90,
        timeout=8,
        only="both",
        current_account_id="shared-acct",
    )
    accounts = payload["accounts"]
    assert sum(1 for item in accounts if item["current"]) == 1
