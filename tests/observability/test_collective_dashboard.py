from __future__ import annotations

from cdx_proxy_cli_v2.observability.collective_dashboard import (
    _window_text,
    build_collective_payload,
    collective_sort_key,
    format_left_percent,
    status_rank,
    account_has_data,
    account_best_left,
)


def test_format_left_percent_known_percent() -> None:
    assert format_left_percent(25) == "75% left"


def test_format_left_percent_unknown_percent() -> None:
    assert format_left_percent(None) == "unknown left"


def test_window_text_includes_left_only() -> None:
    text = _window_text(
        {"status": "OK", "used_percent": 50, "reset_after_seconds": 120}
    )
    plain = text.plain
    assert "50% left" in plain
    assert "reset 2m" in plain


def test_status_rank_order() -> None:
    """OK should have lowest rank (best), UNKNOWN highest (worst)."""
    assert status_rank("OK") == 0
    assert status_rank("WARN") == 1
    assert status_rank("COOLDOWN") == 2
    assert status_rank("UNKNOWN") == 3
    assert status_rank("invalid") == 4


def test_account_has_data() -> None:
    """Should detect if account has usage data."""
    assert account_has_data({"five_hour": {"used_percent": 50}}) is True
    assert account_has_data({"weekly": {"used_percent": 0}}) is True
    assert account_has_data({"five_hour": {}}) is False
    assert account_has_data({}) is False


def test_account_best_left() -> None:
    """Should return highest left percentage."""
    assert account_best_left({"five_hour": {"used_percent": 20}}) == 80.0
    assert (
        account_best_left(
            {"five_hour": {"used_percent": 50}, "weekly": {"used_percent": 10}}
        )
        == 90.0
    )  # weekly has more left
    assert account_best_left({}) is None


def test_collective_sort_key_ok_before_unknown() -> None:
    """OK accounts should sort before UNKNOWN accounts."""
    ok_entry = {"status": "OK", "file": "a.json", "five_hour": {"used_percent": 50}}
    unknown_entry = {"status": "UNKNOWN", "file": "b.json"}

    assert collective_sort_key(ok_entry) < collective_sort_key(unknown_entry)


def test_collective_sort_key_more_left_first() -> None:
    """Within same status, accounts with more left% should come first."""
    entry_80_left = {
        "status": "OK",
        "file": "a.json",
        "five_hour": {"used_percent": 20},
    }
    entry_50_left = {
        "status": "OK",
        "file": "b.json",
        "five_hour": {"used_percent": 50},
    }
    entry_10_left = {
        "status": "OK",
        "file": "c.json",
        "five_hour": {"used_percent": 90},
    }

    # 80% left should come before 50% left
    assert collective_sort_key(entry_80_left) < collective_sort_key(entry_50_left)
    # 50% left should come before 10% left
    assert collective_sort_key(entry_50_left) < collective_sort_key(entry_10_left)


def test_collective_sort_key_with_data_before_without() -> None:
    """Accounts with usage data should sort before accounts with unknown data."""
    with_data = {"status": "OK", "file": "a.json", "five_hour": {"used_percent": 90}}
    without_data = {"status": "OK", "file": "b.json"}

    # Account with data (even heavily used) should come before unknown
    assert collective_sort_key(with_data) < collective_sort_key(without_data)


def test_collective_sort_key_warn_between_ok_and_cooldown() -> None:
    """WARN should be between OK and COOLDOWN."""
    ok_entry = {"status": "OK", "file": "a.json", "five_hour": {"used_percent": 50}}
    warn_entry = {"status": "WARN", "file": "b.json", "five_hour": {"used_percent": 50}}
    cooldown_entry = {
        "status": "COOLDOWN",
        "file": "c.json",
        "five_hour": {"used_percent": 50},
    }

    assert collective_sort_key(ok_entry) < collective_sort_key(warn_entry)
    assert collective_sort_key(warn_entry) < collective_sort_key(cooldown_entry)


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


def test_build_collective_payload_account_id_collision_marks_single_current(
    monkeypatch,
) -> None:
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
