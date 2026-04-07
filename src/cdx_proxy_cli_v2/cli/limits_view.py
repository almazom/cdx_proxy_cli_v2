from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from rich.console import Console
from rich.table import Table

from cdx_proxy_cli_v2.observability.event_log import tail_lines
from cdx_proxy_cli_v2.observability.limits_history import limits_history_path

NO_LIMITS_SNAPSHOT_MESSAGE = (
    "No persisted limits snapshot found. Open `cdx trace` or query /trace first."
)


def _format_limit_percent(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):.1f}%"


def _format_limit_duration(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    total = int(value)
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


def _format_limit_age(ts: object) -> str:
    if not isinstance(ts, (int, float)):
        return "-"
    delta = max(0, int(time.time() - float(ts)))
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _guarded_windows_label(account: Dict[str, Any]) -> str:
    floor = account.get("selection_floor_percent")
    floor_value = float(floor) if isinstance(floor, (int, float)) else None
    labels: list[str] = []
    for key, label in (("five_hour", "5h"), ("weekly", "weekly")):
        window = account.get(key)
        if not isinstance(window, dict):
            continue
        used = window.get("used_percent")
        if not isinstance(used, (int, float)):
            continue
        remaining = max(0.0, 100.0 - float(used))
        if floor_value is not None and remaining < floor_value:
            labels.append(label)
    return "+".join(labels)


def _limit_guard_label(account: Dict[str, Any]) -> str:
    if str(account.get("selection_source") or "").strip().lower() == "degraded":
        label = _guarded_windows_label(account)
        return label or "guard"
    if str(account.get("reason_origin") or "").strip() != "limit_guardrail":
        return "-"
    reason = str(account.get("reason") or "").strip().lower()
    has_5h = "5h" in reason
    has_weekly = "weekly" in reason
    if has_5h and has_weekly:
        return "5h+weekly"
    if has_weekly:
        return "weekly"
    if has_5h:
        return "5h"
    return "guard"


def _limit_window(record: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = record.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _load_limits_history(auth_dir: str, *, tail: int) -> List[Dict[str, Any]]:
    if tail <= 0:
        return []
    lines = tail_lines(limits_history_path(auth_dir), limit=tail)
    records: List[Dict[str, Any]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except Exception:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _render_limits_snapshot(snapshot: Dict[str, Any]) -> None:
    accounts_raw = snapshot.get("accounts")
    accounts = (
        [item for item in accounts_raw if isinstance(item, dict)]
        if isinstance(accounts_raw, list)
        else []
    )
    fetched_at = snapshot.get("fetched_at")
    title = "cdx limits"
    if bool(snapshot.get("stale")):
        title = f"{title} | stale"
    if snapshot.get("error"):
        title = f"{title} | fetch-error"
    table = Table(title=title)
    table.add_column("Account")
    table.add_column("State")
    table.add_column("5H")
    table.add_column("5H Reset")
    table.add_column("Week")
    table.add_column("W Reset")
    table.add_column("Guard")
    table.add_column("Fetched")
    for account in sorted(
        accounts, key=lambda item: str(item.get("email") or item.get("file") or "")
    ):
        five_hour = _limit_window(account, "five_hour")
        weekly = _limit_window(account, "weekly")
        table.add_row(
            str(account.get("email") or account.get("file") or "-"),
            str(account.get("status") or "-"),
            _format_limit_percent(five_hour.get("used_percent")),
            _format_limit_duration(five_hour.get("reset_after_seconds")),
            _format_limit_percent(weekly.get("used_percent")),
            _format_limit_duration(weekly.get("reset_after_seconds")),
            _limit_guard_label(account),
            _format_limit_age(fetched_at),
        )
    Console().print(table)


def _render_limits_history(records: List[Dict[str, Any]]) -> None:
    table = Table(title="cdx limits history")
    table.add_column("Ts")
    table.add_column("Account")
    table.add_column("State")
    table.add_column("5H")
    table.add_column("Week")
    table.add_column("Reason")
    for record in records:
        five_hour = _limit_window(record, "five_hour")
        weekly = _limit_window(record, "weekly")
        table.add_row(
            _format_limit_age(record.get("ts")),
            str(record.get("email") or record.get("file") or "-"),
            str(record.get("status") or "-"),
            _format_limit_percent(five_hour.get("used_percent")),
            _format_limit_percent(weekly.get("used_percent")),
            str(record.get("reason") or "-"),
        )
    Console().print(table)
