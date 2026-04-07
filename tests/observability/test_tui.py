from __future__ import annotations

from cdx_proxy_cli_v2.observability.tui import (
    _current_auth_identity,
    _event_line,
    _limit_account_label,
    _limit_reason_label,
    _limit_row,
    _limit_sort_key,
    _limit_state_label,
    _limits_summary_line,
    order_events_latest_first,
    trim_request_preview,
)


def test_trace_tui_event_line_falls_back_to_path_route() -> None:
    event = {
        "ts": None,
        "auth_file": "a.json",
        "path": "/responses?x=1",
    }
    age, account, status, message, route = _event_line(event, show_preview=False)
    assert age == "-"
    assert account == "a.json"
    assert status == "-"
    assert message == ""
    assert route == "responses"


def test_trace_tui_event_line_labels_websocket_handshake() -> None:
    event = {
        "ts": None,
        "auth_file": "a.json",
        "path": "/responses?x=1",
        "method": "GET",
        "status": 101,
    }
    _age, _account, _status, _message, route = _event_line(event, show_preview=False)
    assert route == "ws"


def test_trace_tui_orders_latest_by_id() -> None:
    ordered = order_events_latest_first(
        [
            {"id": 1, "ts": 100.0},
            {"id": 3, "ts": 90.0},
            {"id": 2, "ts": 110.0},
        ]
    )
    assert [item["id"] for item in ordered] == [3, 2, 1]


def test_trace_tui_trims_and_compacts_preview() -> None:
    raw = "hello     world with   extra spaces"
    assert trim_request_preview(raw, width=12) == "hello world ..."


def test_trace_tui_marks_limit_reason_source() -> None:
    account = {
        "reason": "limit_weekly_and_5h_guardrail",
        "reason_origin": "limit_guardrail",
    }
    assert _limit_reason_label(account) == "5h+weekly guard"


def test_trace_tui_marks_degraded_selection_without_cooldown_reason() -> None:
    account = {
        "status": "WARN",
        "selection_source": "degraded",
        "selection_floor_percent": 30.0,
        "five_hour": {"used_percent": 89.5, "reset_after_seconds": 1800},
        "weekly": {"used_percent": 41.0, "reset_after_seconds": 250000},
    }
    assert _limit_reason_label(account) == "5h guard"


def test_trace_tui_formats_limit_row() -> None:
    row = _limit_row(
        {
            "email": "a@example.com",
            "status": "WARN",
            "cooldown_seconds": 1800,
            "five_hour": {"used_percent": 89.5, "reset_after_seconds": 1800},
            "weekly": {"used_percent": 41.0, "reset_after_seconds": 250000},
            "reason": "limit_5h_guardrail",
            "reason_origin": "limit_guardrail",
        },
        1000.0,
    )
    assert row[0] == "a@example.com"
    assert row[1] == "hot"
    assert row[2] == "5h guard"
    assert row[3] == "30m"
    assert row[4] == "10.5% left / 30m"


def test_trace_tui_translates_internal_limit_state_labels() -> None:
    assert _limit_state_label({"status": "OK"}) == "available"
    assert _limit_state_label({"status": "WARN"}) == "hot"
    assert (
        _limit_state_label(
            {"status": "COOLDOWN", "reason_origin": "limit_guardrail"}
        )
        == "guarded"
    )
    assert (
        _limit_state_label({"status": "COOLDOWN", "reason_origin": "limit"})
        == "limited"
    )
    assert _limit_state_label({"status": "BLACKLIST"}) == "blacklisted"


def test_trace_tui_summary_includes_next_key_metric() -> None:
    summary = _limits_summary_line(
        [
            {
                "status": "WARN",
                "five_hour": {"used_percent": 80.0},
                "weekly": {"used_percent": 50.0},
            },
            {
                "status": "COOLDOWN",
                "cooldown_seconds": 120,
                "five_hour": {"used_percent": 90.0},
                "weekly": {"used_percent": 70.0},
            },
        ],
        fetched_at=1000.0,
    )
    assert "Healthy now 50.0% (1/2)" in summary.plain
    assert "Next key 2m" in summary.plain


def test_trace_tui_marks_current_auth_with_green_dot() -> None:
    current_auth_file, current_auth_email = _current_auth_identity(
        [
            {"id": 2, "auth_file": "b.json", "auth_email": "b@example.com"},
            {"id": 1, "auth_file": "a.json", "auth_email": "a@example.com"},
        ]
    )
    label = _limit_account_label(
        {"file": "b.json", "email": "b@example.com"},
        current_auth_file=current_auth_file,
        current_auth_email=current_auth_email,
    )
    assert label.plain.startswith("🟢 ")


def test_trace_tui_sorts_current_then_available_then_earliest_return() -> None:
    current = {"file": "c.json", "email": "c@example.com", "status": "WARN"}
    available = {"file": "a.json", "email": "a@example.com", "status": "OK"}
    next_pick = {"file": "n.json", "email": "n@example.com", "status": "OK"}
    early_blocked = {
        "file": "b.json",
        "email": "b@example.com",
        "status": "COOLDOWN",
        "reason_origin": "limit",
        "cooldown_seconds": 120,
    }
    later_blocked = {
        "file": "d.json",
        "email": "d@example.com",
        "status": "COOLDOWN",
        "reason_origin": "limit",
        "cooldown_seconds": 240,
    }
    ordered = sorted(
        [later_blocked, available, current, early_blocked, next_pick],
        key=lambda account: _limit_sort_key(
            account,
            current_auth_file="c.json",
            current_auth_email="c@example.com",
            next_auth_file="n.json",
            next_auth_email="n@example.com",
        ),
    )
    assert [item["file"] for item in ordered] == [
        "c.json",
        "n.json",
        "a.json",
        "b.json",
        "d.json",
    ]
