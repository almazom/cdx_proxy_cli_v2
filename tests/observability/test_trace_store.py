from __future__ import annotations

from cdx_proxy_cli_v2.observability.trace_store import TraceStore


def test_trace_store_assigns_ids_and_respects_capacity() -> None:
    store = TraceStore(max_size=2)
    first = store.add({"status": 200})
    second = store.add({"status": 201})
    third = store.add({"status": 202})

    assert first["id"] == 1
    assert second["id"] == 2
    assert third["id"] == 3

    events = store.list()
    assert len(events) == 2
    assert events[0]["id"] == 2
    assert events[1]["id"] == 3
