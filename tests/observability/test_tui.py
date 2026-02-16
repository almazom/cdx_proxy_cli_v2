from __future__ import annotations

from cdx_proxy_cli_v2.observability.tui import _event_line, order_events_latest_first, trim_request_preview


def test_trace_tui_event_line_falls_back_to_path_route() -> None:
    event = {
        "ts": None,
        "auth_file": "a.json",
        "path": "/responses?x=1",
    }
    age, ts, account, status, message, route = _event_line(event, show_preview=False)
    assert age == "-"
    assert ts == "??:??:??"
    assert account == "a.json"
    assert status == "-"
    assert message == ""
    assert route == "request"


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

