from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table

from cdx_proxy_cli_v2.auth.models import AuthRecord


def parse_event_lines(lines: List[str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in lines:
        try:
            raw = json.loads(line)
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        records.append(raw)
    return records


def _parse_ts(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
    return None


def _fmt_ts(value: Any) -> str:
    ts = _parse_ts(value)
    if ts is None:
        return "-"
    try:
        return dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return "-"


def summarize_event_records(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for record in records:
        if record.get("event") != "proxy.request":
            continue
        auth_file = str(record.get("auth_file") or "").strip()
        if not auth_file:
            continue
        status_raw = record.get("status")
        status = int(status_raw) if isinstance(status_raw, int) else None
        item = summary.setdefault(
            auth_file,
            {
                "total": 0,
                "ok_2xx": 0,
                "s401": 0,
                "s429": 0,
                "s5xx": 0,
                "other": 0,
                "last_status": None,
                "last_ts": None,
            },
        )
        item["total"] += 1
        if isinstance(status, int) and 200 <= status < 300:
            item["ok_2xx"] += 1
        elif status == 401:
            item["s401"] += 1
        elif status == 429:
            item["s429"] += 1
        elif isinstance(status, int) and status >= 500:
            item["s5xx"] += 1
        else:
            item["other"] += 1

        current_ts = _parse_ts(record.get("ts"))
        existing_ts = _parse_ts(item.get("last_ts"))
        if existing_ts is None or (current_ts is not None and current_ts >= existing_ts):
            item["last_ts"] = record.get("ts")
            item["last_status"] = status
    return summary


def _health_map(health_payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(health_payload, dict):
        return {}
    accounts = health_payload.get("accounts", [])
    if not isinstance(accounts, list):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for item in accounts:
        if not isinstance(item, dict):
            continue
        key = str(item.get("file") or "").strip()
        if not key:
            continue
        result[key] = item
    return result


def _status_style(status: str) -> str:
    return {
        "OK": "green",
        "COOLDOWN": "yellow",
        "UNKNOWN": "white",
    }.get(status, "white")


def _safe_ratio(ok: int, total: int) -> str:
    if total <= 0:
        return "-"
    return f"{(100.0 * float(ok) / float(total)):.0f}%"


def _shorten(value: str, width: int = 26) -> str:
    text = str(value or "")
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def build_all_payload(
    *,
    service_payload: Dict[str, Any],
    auth_records: List[AuthRecord],
    health_payload: Optional[Dict[str, Any]],
    event_summary: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    health_by_file = _health_map(health_payload)
    known_files = {record.name for record in auth_records}
    known_files.update(event_summary.keys())
    known_files.update(health_by_file.keys())

    def sort_key(name: str) -> tuple:
        health = health_by_file.get(name, {})
        health_status = str(health.get("status") or "UNKNOWN")
        rank = {"OK": 0, "COOLDOWN": 1, "UNKNOWN": 2}.get(health_status, 3)
        stats = event_summary.get(name, {})
        total = int(stats.get("total") or 0)
        ok_2xx = int(stats.get("ok_2xx") or 0)
        success = (float(ok_2xx) / float(total)) if total > 0 else -1.0
        return (rank, -success, -total, name)

    keys: List[Dict[str, Any]] = []
    for name in sorted(known_files, key=sort_key):
        health = health_by_file.get(name, {})
        stats = event_summary.get(name, {})
        health_status = str(health.get("status") or "UNKNOWN")
        cooldown = health.get("cooldown_seconds")
        total = int(stats.get("total") or 0)
        ok_2xx = int(stats.get("ok_2xx") or 0)
        s401 = int(stats.get("s401") or 0)
        s429 = int(stats.get("s429") or 0)
        s5xx = int(stats.get("s5xx") or 0)
        last_status = stats.get("last_status")
        keys.append(
            {
                "file": name,
                "health": health_status,
                "cooldown_seconds": int(cooldown) if isinstance(cooldown, int) else None,
                "stats": {
                    "ok_2xx": ok_2xx,
                    "s401": s401,
                    "s429": s429,
                    "s5xx": s5xx,
                    "other": int(stats.get("other") or 0),
                    "total": total,
                    "success_ratio_percent": round((100.0 * ok_2xx / total), 2) if total > 0 else None,
                },
                "last_status": int(last_status) if isinstance(last_status, int) else None,
                "last_seen": _fmt_ts(stats.get("last_ts")),
            }
        )

    payload: Dict[str, Any] = {
        "summary": {
            "proxy_running": bool(service_payload.get("pid_running")),
            "proxy_healthy": bool(service_payload.get("healthy")),
            "base_url": str(service_payload.get("base_url") or "-"),
            "auth_files_loaded": len(auth_records),
            "events_file": str(service_payload.get("events_file") or "-"),
        },
        "keys": keys,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    return payload


def render_all_dashboard(*, payload: Dict[str, Any]) -> None:
    console = Console()
    summary = payload.get("summary", {})
    rows = payload.get("keys", [])

    summary_table = Table(title="cdx2 all | summary")
    summary_table.add_column("Field")
    summary_table.add_column("Value")
    summary_table.add_row("Proxy running", "yes" if bool(summary.get("proxy_running")) else "no")
    summary_table.add_row("Proxy healthy", "yes" if bool(summary.get("proxy_healthy")) else "no")
    summary_table.add_row("Base URL", str(summary.get("base_url") or "-"))
    summary_table.add_row("Auth files loaded", str(summary.get("auth_files_loaded") or 0))
    summary_table.add_row("Recent events source", str(summary.get("events_file") or "-"))
    console.print(summary_table)

    key_table = Table(title="cdx2 all | keys")
    key_table.add_column("KEY", no_wrap=True)
    key_table.add_column("HEALTH")
    key_table.add_column("COOLDOWN")
    key_table.add_column("2XX")
    key_table.add_column("401")
    key_table.add_column("429")
    key_table.add_column("5XX")
    key_table.add_column("TOTAL")
    key_table.add_column("SUCCESS")
    key_table.add_column("LAST")
    key_table.add_column("AT")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        stats = row.get("stats", {})
        if not isinstance(stats, dict):
            stats = {}
        success_ratio = stats.get("success_ratio_percent")
        success_text = "-" if success_ratio is None else f"{success_ratio:.0f}%"
        cooldown = row.get("cooldown_seconds")
        cooldown_text = str(cooldown) if isinstance(cooldown, int) else "-"
        health_status = str(row.get("health") or "UNKNOWN")
        key_table.add_row(
            _shorten(str(row.get("file") or "-")),
            f"[{_status_style(health_status)}]{health_status}[/{_status_style(health_status)}]",
            cooldown_text,
            str(int(stats.get("ok_2xx") or 0)),
            str(int(stats.get("s401") or 0)),
            str(int(stats.get("s429") or 0)),
            str(int(stats.get("s5xx") or 0)),
            str(int(stats.get("total") or 0)),
            success_text,
            str(row.get("last_status") if row.get("last_status") is not None else "-"),
            str(row.get("last_seen") or "-"),
        )
    console.print(key_table)
