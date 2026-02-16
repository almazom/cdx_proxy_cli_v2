from __future__ import annotations

import datetime as dt
import time
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.proxy.rules import trace_route


def _format_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "??:??:??"
    try:
        return dt.datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return "??:??:??"


def _format_age(ts: Optional[float]) -> str:
    """Format timestamp as relative age like '2s ago', '1m ago', '5m ago'."""
    if ts is None:
        return "-"
    try:
        delta = time.time() - float(ts)
        if delta < 0:
            return "future"
        if delta < 60:
            return f"{int(delta)}s ago"
        if delta < 3600:
            return f"{int(delta / 60)}m ago"
        if delta < 86400:
            return f"{int(delta / 3600)}h ago"
        return f"{int(delta / 86400)}d ago"
    except Exception:
        return "-"


def _shorten_account(name: str, max_len: int = 16) -> str:
    """Shorten email/account for display: first N chars + ellipsis if needed."""
    if not name or name == "-":
        return "-"
    if len(name) <= max_len:
        return name
    # Show first part + ellipsis, try to preserve domain part
    if "@" in name:
        user, domain = name.rsplit("@", 1)
        user_part = user[: max_len - 3 - len(domain)]
        return f"{user_part}…@{domain}"
    return f"{name[: max_len - 1]}…"


def _event_label(event: Dict[str, Any], shorten: bool = True) -> str:
    name = str(event.get("auth_email") or event.get("auth_file") or event.get("auth_id") or "-")
    return _shorten_account(name) if shorten else name


def _event_sort_key(event: Dict[str, Any]) -> Tuple[float, float]:
    event_id = event.get("id")
    if isinstance(event_id, int):
        return float(event_id), float(event.get("ts") or 0.0)
    ts = event.get("ts")
    if isinstance(ts, (int, float)):
        return float(ts), -1.0
    return -1.0, -1.0


def order_events_latest_first(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(events, key=_event_sort_key, reverse=True)


def trim_request_preview(value: object, width: int = 30) -> str:
    raw = str(value or "").strip()
    compact = " ".join(raw.split())
    if not compact:
        return "-"
    if len(compact) > width:
        return f"{compact[:width]}..."
    return compact


def _event_line(event: Dict[str, Any], show_preview: bool = False) -> Tuple[str, str, str, str, str]:
    age = _format_age(event.get("ts"))
    ts = _format_ts(event.get("ts"))
    account = _event_label(event, shorten=True)
    route = str(event.get("route") or trace_route(str(event.get("path") or "")))
    message = trim_request_preview(event.get("request_preview")) if show_preview else ""
    status = str(event.get("status") or "-")
    return age, ts, account, status, message, route


def compute_distribution(events: List[Dict[str, Any]]) -> Tuple[Dict[str, int], int]:
    counts: Dict[str, int] = {}
    total = 0
    for event in events:
        label = _event_label(event)
        counts[label] = counts.get(label, 0) + 1
        total += 1
    return counts, total


def compute_confidence(events: List[Dict[str, Any]]) -> float:
    if not events:
        return 100.0
    counts, total = compute_distribution(events)
    if total <= 0:
        return 100.0
    num_keys = max(len(counts), 1)
    expected = total / num_keys
    if expected <= 0:
        return 100.0
    max_dev = max(abs(count - expected) / expected for count in counts.values())
    confidence = max(0.0, 100.0 - (max_dev * 100))
    return round(confidence, 2)


def adjacent_diff_ratio(events: List[Dict[str, Any]]) -> Optional[float]:
    if not events:
        return None
    if len(events) < 2:
        return 1.0
    labels = [_event_label(event) for event in events]
    total = len(labels) - 1
    diff = 0
    last = labels[0]
    for label in labels[1:]:
        if label != last:
            diff += 1
        last = label
    return diff / total if total else 1.0


class HighlightTracker:
    """Tracks newly appeared events and highlights for a short window."""

    HIGHLIGHT_SECONDS: ClassVar[float] = 5.0

    def __init__(self) -> None:
        self._seen_ids: set[int] = set()
        self._highlight_until: Dict[int, float] = {}
        self._initialized = False

    def update(self, events: List[Dict[str, Any]]) -> Set[int]:
        current_time = time.time()
        ids: List[int] = [int(event["id"]) for event in events if isinstance(event.get("id"), int)]
        current_ids = set(ids)

        if not self._initialized:
            self._initialized = True
            self._seen_ids = current_ids
            return set()

        new_ids = current_ids - self._seen_ids
        for event_id in new_ids:
            self._highlight_until[event_id] = current_time + self.HIGHLIGHT_SECONDS

        for event_id in list(self._highlight_until.keys()):
            if event_id not in current_ids or current_time > self._highlight_until[event_id]:
                self._highlight_until.pop(event_id, None)

        self._seen_ids = current_ids
        return set(self._highlight_until.keys())


def _build_view(
    events: List[Dict[str, Any]],
    *,
    window: int,
    highlight_ids: Set[int],
    base_url: str,
    upstream_base_url: Optional[str] = None,
    log_request_preview: Optional[bool] = None,
    last_error: Optional[str] = None,
) -> Panel:
    show_preview = log_request_preview is True
    title = f"CDX TRACE | latest-first | showing={min(len(events), 20)}"
    if log_request_preview is not None:
        preview_mode = "on" if log_request_preview else "off"
        title = f"{title} | preview={preview_mode}"

    ordered = order_events_latest_first(events)
    table = Table(show_header=True, header_style="bold")
    table.add_column("AGE", style="cyan", no_wrap=True)
    table.add_column("ACCOUNT", style="white")
    table.add_column("S", style="white", no_wrap=True)
    if show_preview:
        table.add_column("MESSAGE", style="white", no_wrap=True)
    table.add_column("ROUTE", style="dim", no_wrap=True)
    for event in ordered[:20]:
        age, ts, account, status, message, route = _event_line(event, show_preview=show_preview)
        ev_id = event.get("id")
        # Color-code status
        try:
            status_code = int(status)
            if 200 <= status_code < 300:
                status_style = "green"
            elif 400 <= status_code < 500:
                status_style = "yellow"
            elif status_code >= 500:
                status_style = "red"
            else:
                status_style = "white"
        except (ValueError, TypeError):
            status_style = "white"
        # Build row with color-coded status
        if isinstance(ev_id, int) and ev_id in highlight_ids:
            if show_preview:
                table.add_row(age, account, Text(status, style=status_style), message, route, style="bold")
            else:
                table.add_row(age, account, Text(status, style=status_style), route, style="bold")
        else:
            if show_preview:
                table.add_row(age, account, Text(status, style=status_style), message, route)
            else:
                table.add_row(age, account, Text(status, style=status_style), route)

    body: Any = table if ordered else Text("no entries")
    if last_error:
        body = Panel(Text(f"error: {last_error}", style="red"), title="Trace Error", expand=True)
    return Panel(body, title=title, expand=True)


def run_trace_tui(
    *,
    base_url: str,
    upstream_base_url: Optional[str] = None,
    log_request_preview: Optional[bool] = None,
    window: int = 200,
    interval: float = 1.0,
    limit: int = 0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> None:
    console = Console()
    tracker = HighlightTracker()
    last_error: Optional[str] = None

    with Live(console=console, auto_refresh=False, screen=False) as live:
        while True:
            try:
                path = "/trace"
                if limit > 0:
                    path = f"/trace?limit={limit}"
                payload = fetch_json(
                    base_url=base_url,
                    path=path,
                    headers=extra_headers,
                    timeout=2.0,
                )
                events_raw = payload.get("events", [])
                if isinstance(events_raw, list):
                    events = [item for item in events_raw if isinstance(item, dict)]
                else:
                    events = []
                highlight_ids = tracker.update(events)
                last_error = None
            except Exception as exc:  # noqa: BLE001
                events = []
                highlight_ids = set()
                last_error = str(exc)

            panel = _build_view(
                events,
                window=window,
                highlight_ids=highlight_ids,
                base_url=base_url,
                upstream_base_url=upstream_base_url,
                log_request_preview=log_request_preview,
                last_error=last_error,
            )
            live.update(panel, refresh=True)
            time.sleep(max(0.1, interval))
