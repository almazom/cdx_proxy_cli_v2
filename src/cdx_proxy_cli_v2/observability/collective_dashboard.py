from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional, Tuple

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cdx_proxy_cli_v2.health_snapshot import collective_health_snapshot
from cdx_proxy_cli_v2.limits_domain import overall_status

OPEN_RIGHT_ROUNDED = box.Box(
    "    \n"
    "│ │ \n"
    "├─┼ \n"
    "│ │ \n"
    "├─┼ \n"
    "├─┼ \n"
    "│ │ \n"
    "╰─┴ \n"
)

OPEN_RIGHT_DOUBLE = box.Box(
    "    \n"
    "║ ║ \n"
    "╠═╬ \n"
    "║ ║ \n"
    "╠═╬ \n"
    "╠═╬ \n"
    "║ ║ \n"
    "╚═╩ \n"
)


def human_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "unknown"
    remaining = max(0, int(seconds))
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, remaining = divmod(remaining, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{remaining}s")
    return " ".join(parts)


def format_percent(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, int):
        return f"{value}%"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value)}%"
    if isinstance(value, (int, float)):
        return f"{value:.1f}%"
    return "unknown"


def left_percent_from_used(used_value: Optional[float]) -> Optional[float]:
    if not isinstance(used_value, (int, float)):
        return None
    return max(0.0, min(100.0, 100.0 - float(used_value)))


def format_left_percent(used_value: Optional[float]) -> str:
    left_value = left_percent_from_used(used_value)
    if left_value is None:
        return "unknown left"
    return f"{format_percent(left_value)} left"


def mini_meter(percent: Optional[float], slots: int = 10) -> str:
    if not isinstance(percent, (int, float)):
        return "▱" * slots
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round((pct / 100.0) * slots))
    filled = max(0, min(slots, filled))
    return ("▰" * filled) + ("▱" * (slots - filled))


def status_level_emoji(status: str) -> str:
    return {
        "OK": "🟢",
        "WARN": "🟡",
        "COOLDOWN": "🔴",
        "UNKNOWN": "⚪",
    }.get(status, "⚪")


def status_rank(status: str) -> int:
    order = {"UNKNOWN": 0, "OK": 1, "WARN": 2, "COOLDOWN": 3}
    return order.get(status, 0)


def account_worst_used(entry: Dict[str, Any]) -> Optional[float]:
    worst_used = None
    for key in ("five_hour", "weekly"):
        window = entry.get(key)
        if isinstance(window, dict):
            used = window.get("used_percent")
            if isinstance(used, (int, float)):
                worst_used = used if worst_used is None else max(worst_used, used)
    return worst_used


def account_min_reset(entry: Dict[str, Any]) -> Optional[int]:
    min_reset = None
    for key in ("five_hour", "weekly"):
        window = entry.get(key)
        if isinstance(window, dict):
            reset_after = window.get("reset_after_seconds")
            if isinstance(reset_after, int):
                min_reset = reset_after if min_reset is None else min(min_reset, reset_after)
    return min_reset


def collective_sort_key(entry: Dict[str, Any]) -> Tuple[float, float, float, str]:
    status = entry.get("status", "UNKNOWN")
    rank = status_rank(status)
    worst_used = account_worst_used(entry)
    min_reset = account_min_reset(entry)
    worst_used_val = worst_used if worst_used is not None else 1e9
    min_reset_val = min_reset if min_reset is not None else 1e18
    return (rank, worst_used_val, min_reset_val, entry.get("file", ""))


def build_collective_payload(
    *,
    auths_dir: str,
    base_url: str,
    warn_at: int,
    cooldown_at: int,
    timeout: int,
    only: str,
    current_access_token: Optional[str] = None,
    current_file: Optional[str] = None,
    current_email: Optional[str] = None,
    current_account_id: Optional[str] = None,
) -> Dict[str, Any]:
    snapshot = collective_health_snapshot(
        auths_dir=auths_dir,
        base_url=base_url,
        warn_at=warn_at,
        cooldown_at=cooldown_at,
        timeout=timeout,
        only=only,
    )
    accounts = snapshot.get("accounts", [])
    counts = {"ok": 0, "warn": 0, "cooldown": 0, "unknown": 0}
    max_used = None
    total_used_percent = 0.0
    total_used_samples = 0
    min_reset = None
    next_available_in = None
    next_available_file = None
    for entry in accounts:
        status = entry.get("status", "UNKNOWN")
        if status == "OK":
            counts["ok"] += 1
        elif status == "WARN":
            counts["warn"] += 1
        elif status == "COOLDOWN":
            counts["cooldown"] += 1
        else:
            counts["unknown"] += 1
        worst_used = account_worst_used(entry)
        if isinstance(worst_used, (int, float)):
            max_used = worst_used if max_used is None else max(max_used, worst_used)
        for window_key in ("five_hour", "weekly"):
            window = entry.get(window_key)
            if not isinstance(window, dict):
                continue
            used = window.get("used_percent")
            if isinstance(used, (int, float)):
                total_used_percent += float(used)
                total_used_samples += 1
        min_reset_entry = account_min_reset(entry)
        if isinstance(min_reset_entry, int):
            min_reset = min_reset_entry if min_reset is None else min(min_reset, min_reset_entry)
            if status == "COOLDOWN":
                if next_available_in is None or min_reset_entry < next_available_in:
                    next_available_in = min_reset_entry
                    next_available_file = entry.get("file")

    aggregate_status = overall_status([entry.get("status", "UNKNOWN") for entry in accounts])
    global_exhaustion = (
        (total_used_percent / float(total_used_samples)) if total_used_samples > 0 else None
    )
    aggregate = {
        "status": aggregate_status,
        "counts": counts,
        "global_exhaustion": global_exhaustion,
        "max_used": max_used,
        "min_reset_seconds": min_reset,
        "total": len(accounts),
    }
    availability = {
        "available_now": counts["ok"] + counts["warn"],
        "cooldown_now": counts["cooldown"],
        "unknown_now": counts["unknown"],
        "next_available_in_seconds": next_available_in,
        "next_available_file": next_available_file,
    }

    def _pick_current_candidates() -> list[Dict[str, Any]]:
        if current_file:
            matched = [entry for entry in accounts if entry.get("file") == current_file]
            if matched:
                return matched
        if current_access_token:
            matched = [entry for entry in accounts if entry.get("access_token") == current_access_token]
            if matched:
                return matched
        if current_email:
            needle = current_email.strip().lower()
            matched = [
                entry
                for entry in accounts
                if isinstance(entry.get("email"), str) and entry.get("email", "").strip().lower() == needle
            ]
            if matched:
                return matched
        if current_account_id:
            matched = [entry for entry in accounts if entry.get("account_id") == current_account_id]
            if matched:
                return matched
        return []

    for entry in accounts:
        entry["current"] = False

    matched_entries = _pick_current_candidates()
    if matched_entries:
        selected = sorted(matched_entries, key=collective_sort_key)[0]
        selected["current"] = True
    elif accounts:
        selected = sorted(accounts, key=collective_sort_key)[0]
        selected["current"] = True

    for entry in accounts:
        entry.pop("access_token", None)
        entry.pop("account_id", None)

    return {
        "ok": True,
        "aggregate": aggregate,
        "availability": availability,
        "accounts": accounts,
        "thresholds": {"warn_at": warn_at, "cooldown_at": cooldown_at, "only": only},
        "retrieved_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
    }


def _window_text(window: Optional[Dict[str, Any]]) -> Text:
    if not isinstance(window, dict):
        return Text("unknown")
    status = window.get("status", "UNKNOWN")
    used_value = window.get("used_percent") if isinstance(window.get("used_percent"), (int, float)) else None
    left_value = left_percent_from_used(used_value)
    usage_text = format_left_percent(used_value)
    bar_text = mini_meter(left_value)
    reset_text = human_duration(
        window.get("reset_after_seconds") if isinstance(window.get("reset_after_seconds"), int) else None
    )
    color = {"OK": "green", "WARN": "yellow", "COOLDOWN": "red", "UNKNOWN": "white"}.get(status, "white")
    return Text(f"{bar_text}  {usage_text} | reset {reset_text}", style=color)


def render_collective_dashboard(payload: Dict[str, Any]) -> None:
    console = Console()
    aggregate = payload.get("aggregate", {})
    global_exhaustion = aggregate.get("global_exhaustion")
    global_left = left_percent_from_used(global_exhaustion)
    left_text = format_percent(global_left) if isinstance(global_left, (int, float)) else "unknown"
    console.print(f"Global left: {left_text}  {mini_meter(global_left)}")

    accounts = payload.get("accounts", [])
    current = [account for account in accounts if account.get("current")]
    rest = [account for account in accounts if not account.get("current")]
    rest.sort(key=collective_sort_key)

    panels = []
    current_panels = []
    for entry in current + rest:
        file_name = entry.get("file", "unknown")
        email = entry.get("email") or "unknown"
        status = entry.get("status", "UNKNOWN")
        star = "⭐ " if entry.get("current") else ""
        key_label = f"{file_name} {status_level_emoji(status)}"

        five_hour = _window_text(entry.get("five_hour"))
        weekly = _window_text(entry.get("weekly"))
        body = Table.grid(padding=(0, 1))
        body.add_column(justify="left")
        body.add_column(justify="left")
        body.add_row("Key", Text(key_label))
        body.add_row("Email", Text(f"{star}{email}"))
        body.add_row("5h", five_hour)
        body.add_row("Weekly", weekly)
        if entry.get("current"):
            panel_box = OPEN_RIGHT_DOUBLE
            border_style = "bold bright_white"
        else:
            panel_box = OPEN_RIGHT_ROUNDED
            border_style = "white"
        panel = Panel(body, expand=False, box=panel_box, border_style=border_style)
        if entry.get("current"):
            current_panels.append(panel)
        else:
            panels.append(panel)

    if current_panels:
        console.print()
        for panel in current_panels:
            console.print(panel)
        console.print()
    if panels:
        console.print(Columns(panels, equal=True, expand=True))
    else:
        console.print("No auth keys found in ~/.codex/_auths")
