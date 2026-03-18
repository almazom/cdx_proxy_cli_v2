from __future__ import annotations

import time
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.proxy.rules import trace_route


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
    name = str(
        event.get("auth_email") or event.get("auth_file") or event.get("auth_id") or "-"
    )
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


def _format_percent(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):.1f}%"


def _format_duration(seconds: object) -> str:
    if not isinstance(seconds, (int, float)):
        return "-"
    total = int(seconds)
    if total <= 0:
        return "-"
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    if total < 86400:
        hours = total // 3600
        minutes = (total % 3600) // 60
        return f"{hours}h{minutes:02d}m" if minutes else f"{hours}h"
    days = total // 86400
    hours = (total % 86400) // 3600
    return f"{days}d{hours:02d}h" if hours else f"{days}d"


def _format_remaining_percent(window: object) -> str:
    if not isinstance(window, dict):
        return "-"
    used = window.get("used_percent")
    if not isinstance(used, (int, float)):
        return "-"
    remaining = max(0.0, 100.0 - float(used))
    return f"{remaining:.1f}% left"


def _limit_reason_label(account: Dict[str, Any]) -> str:
    reason = str(account.get("reason") or "").strip().lower()
    origin = str(account.get("reason_origin") or "").strip().lower()
    if not reason:
        return "-"
    if reason == "runtime_unavailable":
        return "runtime"
    if reason == "limit_unavailable":
        return "no limits"
    has_5h = "5h" in reason
    has_weekly = "weekly" in reason
    base = "-"
    if has_5h and has_weekly:
        base = "5h+weekly"
    elif has_weekly:
        base = "weekly"
    elif has_5h:
        base = "5h"
    if origin == "limit_guardrail" and base != "-":
        return f"{base} guard"
    if origin == "limit" and base != "-":
        return base
    return reason.replace("_", " ")


def _limit_state_label(account: Dict[str, Any]) -> str:
    status = str(account.get("status") or "").strip().upper()
    origin = str(account.get("reason_origin") or "").strip().lower()
    reason = str(account.get("reason") or "").strip().lower()
    if status == "OK":
        return "available"
    if status == "WARN":
        return "hot"
    if status == "COOLDOWN":
        if origin == "limit_guardrail":
            return "guarded"
        if origin == "limit":
            return "limited"
        return "cooling"
    if status == "PROBATION":
        return "probing"
    if status == "BLACKLIST":
        return "blacklisted"
    if reason == "runtime_unavailable":
        return "runtime"
    return "unknown"


def _limit_return_label(account: Dict[str, Any]) -> str:
    remaining = _limit_return_seconds(account)
    if remaining is not None and remaining > 0:
        return _format_duration(remaining)
    return "-"


def _limit_return_seconds(account: Dict[str, Any]) -> Optional[int]:
    cooldown_seconds = account.get("cooldown_seconds")
    if isinstance(cooldown_seconds, (int, float)) and int(cooldown_seconds) > 0:
        return int(cooldown_seconds)
    until = account.get("until")
    if isinstance(until, (int, float)):
        remaining = int(float(until) - time.time())
        if remaining > 0:
            return remaining
    return None


def _limit_window_summary(window: object) -> str:
    if not isinstance(window, dict):
        return "-"
    remaining = _format_remaining_percent(window)
    reset = _format_duration(window.get("reset_after_seconds"))
    if remaining == "-" and reset == "-":
        return "-"
    if reset == "-":
        return remaining
    if remaining == "-":
        return reset
    return f"{remaining} / {reset}"


def _limits_summary_line(accounts: List[Dict[str, Any]], *, fetched_at: Optional[float]) -> Text:
    total = len(accounts)
    if total <= 0:
        return Text("No limit snapshots loaded.", style="dim")
    healthy = 0
    warn = 0
    cooldown = 0
    blacklist = 0
    unknown = 0
    five_hour_remaining: List[float] = []
    weekly_remaining: List[float] = []
    next_return_seconds: Optional[int] = None
    for account in accounts:
        status = str(account.get("status") or "").upper()
        if status == "OK":
            healthy += 1
        elif status == "WARN":
            warn += 1
        elif status == "COOLDOWN":
            cooldown += 1
        elif status == "BLACKLIST":
            blacklist += 1
        else:
            unknown += 1
        if status not in {"OK", "WARN"}:
            candidate = _limit_return_seconds(account) or 0
            if candidate > 0 and (
                next_return_seconds is None or candidate < next_return_seconds
            ):
                next_return_seconds = candidate
        five_hour = account.get("five_hour")
        if isinstance(five_hour, dict):
            used = five_hour.get("used_percent")
            if isinstance(used, (int, float)):
                five_hour_remaining.append(max(0.0, 100.0 - float(used)))
        weekly = account.get("weekly")
        if isinstance(weekly, dict):
            used = weekly.get("used_percent")
            if isinstance(used, (int, float)):
                weekly_remaining.append(max(0.0, 100.0 - float(used)))
    healthy_now = healthy + warn
    healthy_pct = (healthy_now / total) * 100.0
    avg_5h = (
        f"{(sum(five_hour_remaining) / len(five_hour_remaining)):.1f}%"
        if five_hour_remaining
        else "-"
    )
    avg_week = (
        f"{(sum(weekly_remaining) / len(weekly_remaining)):.1f}%"
        if weekly_remaining
        else "-"
    )
    next_key = _format_duration(next_return_seconds) if next_return_seconds else "-"
    fetched = _format_age(fetched_at)
    return Text(
        " | ".join(
            [
                f"Healthy now {healthy_pct:.1f}% ({healthy_now}/{total})",
                f"OK {healthy}",
                f"WARN {warn}",
                f"COOLDOWN {cooldown}",
                f"BLACKLIST {blacklist}",
                f"UNKNOWN {unknown}",
                f"Next key {next_key}",
                f"Avg 5H left {avg_5h}",
                f"Avg week left {avg_week}",
                f"Fetched {fetched}",
            ]
        ),
        style="cyan",
    )


def _current_auth_identity(events: List[Dict[str, Any]]) -> Tuple[str, str]:
    for event in order_events_latest_first(events):
        auth_file = str(event.get("auth_file") or "").strip()
        auth_email = str(event.get("auth_email") or "").strip()
        if auth_file or auth_email:
            return auth_file, auth_email
    return "", ""


def _limit_account_label(
    account: Dict[str, Any], *, current_auth_file: str, current_auth_email: str
) -> Text:
    account_name = str(account.get("email") or account.get("file") or "-")
    account_file = str(account.get("file") or "").strip()
    account_email = str(account.get("email") or "").strip()
    is_current = bool(
        (current_auth_file and account_file == current_auth_file)
        or (current_auth_email and account_email == current_auth_email)
    )
    if is_current:
        return Text(f"🟢 {account_name}", style="green")
    return Text(account_name)


def _is_current_limit_account(
    account: Dict[str, Any], *, current_auth_file: str, current_auth_email: str
) -> bool:
    account_file = str(account.get("file") or "").strip()
    account_email = str(account.get("email") or "").strip()
    return bool(
        (current_auth_file and account_file == current_auth_file)
        or (current_auth_email and account_email == current_auth_email)
    )


def _is_next_limit_account(
    account: Dict[str, Any], *, next_auth_file: str, next_auth_email: str
) -> bool:
    account_file = str(account.get("file") or "").strip()
    account_email = str(account.get("email") or "").strip()
    return bool(
        (next_auth_file and account_file == next_auth_file)
        or (next_auth_email and account_email == next_auth_email)
    )


def _limit_sort_key(
    account: Dict[str, Any], *, current_auth_file: str, current_auth_email: str, next_auth_file: str = "", next_auth_email: str = ""
) -> Tuple[int, int, str]:
    is_current = _is_current_limit_account(
        account,
        current_auth_file=current_auth_file,
        current_auth_email=current_auth_email,
    )
    if is_current:
        return (0, 0, str(account.get("email") or account.get("file") or ""))
    is_next = _is_next_limit_account(
        account,
        next_auth_file=next_auth_file,
        next_auth_email=next_auth_email,
    )
    if is_next:
        return (1, 0, str(account.get("email") or account.get("file") or ""))
    state = _limit_state_label(account)
    if state in {"available", "hot"}:
        state_rank = 1 if state == "available" else 2
        return (2, state_rank, str(account.get("email") or account.get("file") or ""))
    return_seconds = _limit_return_seconds(account)
    if return_seconds is not None and return_seconds > 0:
        return (3, return_seconds, str(account.get("email") or account.get("file") or ""))
    return (4, 0, str(account.get("email") or account.get("file") or ""))


def _limit_row(account: Dict[str, Any], fetched_at: Optional[float]) -> Tuple[str, ...]:
    return (
        str(account.get("email") or account.get("file") or "-"),
        _limit_state_label(account),
        _limit_reason_label(account),
        _limit_return_label(account),
        _limit_window_summary(account.get("five_hour")),
        _limit_window_summary(account.get("weekly")),
        _format_age(fetched_at),
    )


def _event_line(
    event: Dict[str, Any], show_preview: bool = False
) -> Tuple[str, str, str, str, str]:
    age = _format_age(event.get("ts"))
    # Show full account identity in table rows to avoid collisions like
    # almazomam@gmail.com vs almazomru@gmail.com both becoming alma…@gmail.com.
    account = _event_label(event, shorten=False)
    route = str(event.get("route") or trace_route(str(event.get("path") or ""))).strip()
    message = trim_request_preview(event.get("request_preview")) if show_preview else ""
    status = str(event.get("status") or "-")
    method = str(event.get("method") or "").upper()
    if route == "responses" and status == "101":
        route = "ws"
    elif route == "responses" and method == "POST":
        route = "responses"
    elif route == "management":
        route = "mgmt"
    elif not route:
        route = "-"
    return age, account, status, message, route


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
        ids: List[int] = [
            int(event["id"]) for event in events if isinstance(event.get("id"), int)
        ]
        current_ids = set(ids)

        if not self._initialized:
            self._initialized = True
            self._seen_ids = current_ids
            return set()

        new_ids = current_ids - self._seen_ids
        for event_id in new_ids:
            self._highlight_until[event_id] = current_time + self.HIGHLIGHT_SECONDS

        for event_id in list(self._highlight_until.keys()):
            if (
                event_id not in current_ids
                or current_time > self._highlight_until[event_id]
            ):
                self._highlight_until.pop(event_id, None)

        self._seen_ids = current_ids
        return set(self._highlight_until.keys())


def _build_limits_panel(
    limits: Dict[str, Any], *, current_auth_file: str = "", current_auth_email: str = ""
) -> Panel:
    fetched_at = limits.get("fetched_at")
    fetched_value = float(fetched_at) if isinstance(fetched_at, (int, float)) else None
    stale = bool(limits.get("stale"))
    error = str(limits.get("error") or "").strip()
    next_auth_file = str(limits.get("next_auth_file") or "").strip()
    next_auth_email = str(limits.get("next_auth_email") or "").strip()
    accounts_raw = limits.get("accounts")
    accounts = [item for item in accounts_raw if isinstance(item, dict)] if isinstance(accounts_raw, list) else []

    title = "LIMITS"
    if stale:
        title = f"{title} | stale"
    if error:
        title = f"{title} | fetch-error"

    table = Table(show_header=True, header_style="bold")
    table.add_column("ACCOUNT", style="white")
    table.add_column("STATE", style="white", no_wrap=True)
    table.add_column("WHY", style="white", no_wrap=True)
    table.add_column("RETURN", style="white", no_wrap=True)
    table.add_column("5H", style="white", no_wrap=True)
    table.add_column("WEEK", style="white", no_wrap=True)
    table.add_column("FETCHED", style="dim", no_wrap=True)

    if accounts:
        summary = _limits_summary_line(accounts, fetched_at=fetched_value)
        sorted_accounts = sorted(
            accounts,
            key=lambda account: _limit_sort_key(
                account,
                current_auth_file=current_auth_file,
                current_auth_email=current_auth_email,
                next_auth_file=next_auth_file,
                next_auth_email=next_auth_email,
            ),
        )
        for account in sorted_accounts:
            row = _limit_row(account, fetched_value)
            state = row[1]
            state_style = "white"
            if state == "available":
                state_style = "green"
            elif state in {"hot", "probing"}:
                state_style = "yellow"
            elif state in {"guarded", "limited", "cooling", "blacklisted"}:
                state_style = "red"
            table.add_row(
                _limit_account_label(
                    account,
                    current_auth_file=current_auth_file,
                    current_auth_email=current_auth_email,
                ),
                Text(state, style=state_style),
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
            )
        body: Any = Group(summary, table)
    else:
        status = "limits unavailable"
        if error:
            status = f"{status}: {error}"
        body = Text(status)
    return Panel(body, title=title, expand=True)


def _build_events_panel(
    events: List[Dict[str, Any]],
    *,
    highlight_ids: Set[int],
    log_request_preview: Optional[bool] = None,
    last_error: Optional[str] = None,
) -> Panel:
    show_preview = log_request_preview is True
    ordered = [
        event
        for event in order_events_latest_first(events)
        if _event_line(event, show_preview=show_preview)[4] != "-"
    ]
    title = f"CDX TRACE | latest-first | showing={min(len(ordered), 20)}"
    if log_request_preview is not None:
        preview_mode = "on" if log_request_preview else "off"
        title = f"{title} | preview={preview_mode}"
    table = Table(show_header=True, header_style="bold")
    table.add_column("AGE", style="cyan", no_wrap=True)
    table.add_column("ACCOUNT", style="white")
    table.add_column("S", style="white", no_wrap=True)
    if show_preview:
        table.add_column("MESSAGE", style="white", no_wrap=True)
    table.add_column("ROUTE", style="dim", no_wrap=True)
    for event in ordered[:20]:
        age, account, status, message, route = _event_line(
            event, show_preview=show_preview
        )
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
                table.add_row(
                    age,
                    account,
                    Text(status, style=status_style),
                    message,
                    route,
                    style="bold",
                )
            else:
                table.add_row(
                    age, account, Text(status, style=status_style), route, style="bold"
                )
        else:
            if show_preview:
                table.add_row(
                    age, account, Text(status, style=status_style), message, route
                )
            else:
                table.add_row(age, account, Text(status, style=status_style), route)

    body: Any = table if ordered else Text("no entries")
    if last_error:
        body = Panel(
            Text(f"error: {last_error}", style="red"), title="Trace Error", expand=True
        )
    return Panel(body, title=title, expand=True)


def _build_view(
    events: List[Dict[str, Any]],
    *,
    window: int,
    highlight_ids: Set[int],
    base_url: str,
    upstream_base_url: Optional[str] = None,
    log_request_preview: Optional[bool] = None,
    last_error: Optional[str] = None,
    limits: Optional[Dict[str, Any]] = None,
) -> Group:
    _ = window
    _ = base_url
    _ = upstream_base_url
    current_auth_file, current_auth_email = _current_auth_identity(events)
    limits_panel = _build_limits_panel(
        limits or {},
        current_auth_file=current_auth_file,
        current_auth_email=current_auth_email,
    )
    events_panel = _build_events_panel(
        events,
        highlight_ids=highlight_ids,
        log_request_preview=log_request_preview,
        last_error=last_error,
    )
    return Group(limits_panel, events_panel)


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
                limits = payload.get("limits", {})
                if not isinstance(limits, dict):
                    limits = {}
                highlight_ids = tracker.update(events)
                last_error = None
            except Exception as exc:  # noqa: BLE001
                events = []
                limits = {}
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
                limits=limits,
            )
            live.update(panel, refresh=True)
            time.sleep(max(0.1, interval))
