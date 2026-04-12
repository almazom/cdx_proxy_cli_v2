from __future__ import annotations

import argparse
import json

from rich.console import Console
from rich.table import Table

from cdx_proxy_cli_v2.runtime.service import service_status

from cdx_proxy_cli_v2.cli.shared import _settings_from_args


def _format_duration(seconds: object) -> str:
    if not isinstance(seconds, (int, float)):
        return "never"
    if float(seconds) < 1.0:
        return "<1s"
    return f"{int(seconds)}s"


def handle_status(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    payload = service_status(settings)
    triage_summary = payload.get("triage_summary")
    if not isinstance(triage_summary, dict):
        triage_summary = None
    triage = payload.get("triage")
    if not isinstance(triage, dict):
        triage = None
    pool_health = payload.get("pool_health")
    if not isinstance(pool_health, list):
        pool_health = []

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0

    table = Table(title="cdx service status")
    table.add_column("Field")
    table.add_column("Value")
    for key in [
        "pid",
        "pid_running",
        "healthy",
        "base_url",
        "host",
        "port",
        "auth_count",
        "state",
        "log_file",
        "events_file",
    ]:
        table.add_row(key, str(payload.get(key)))
    console = Console()
    console.print(table)
    if triage_summary:
        state = str(triage_summary.get("state") or "unknown").upper()
        ok_count = triage_summary.get("ok_count")
        total = triage_summary.get("total")
        cooldown_count = triage_summary.get("cooldown_count")
        blacklist_count = triage_summary.get("blacklist_count")
        next_action = str(triage_summary.get("next_action") or "").strip()
        detail_parts = []
        if ok_count is not None and total is not None:
            detail_parts.append(f"{ok_count}/{total} ok")
        if cooldown_count:
            detail_parts.append(f"{cooldown_count} cooldown")
        if blacklist_count:
            detail_parts.append(f"{blacklist_count} blacklist")
        details = ", ".join(detail_parts)
        verdict_line = f"Pool state: {state}"
        if details:
            verdict_line += f" ({details})"
        if next_action:
            verdict_line += f" -> {next_action}"
        console.print(verdict_line)

    if getattr(args, "verbose", False) and triage:
        triage_table = Table(title="pool triage")
        triage_table.add_column("Field")
        triage_table.add_column("Value")
        triage_table.add_row("summary", str(triage.get("summary")))
        triage_table.add_row("risk_level", str(triage.get("risk_level")))
        triage_table.add_row("auto_reset_status", str(triage.get("auto_reset_status")))
        triage_table.add_row("next_action", str(triage.get("next_action") or "-"))
        console.print(triage_table)

    if getattr(args, "verbose", False) and pool_health:
        pool_table = Table(title="pool health")
        pool_table.add_column("File")
        pool_table.add_column("Status")
        pool_table.add_column("Weight")
        pool_table.add_column("Pick %")
        pool_table.add_column("Last Pick")
        pool_table.add_column("Starvation Risk")
        for item in pool_health:
            pool_table.add_row(
                str(item.get("file") or "-"),
                str(item.get("status") or "-"),
                f"{float(item.get('weight') or 0.0):.2f}",
                f"{float(item.get('effective_pick_probability') or 0.0) * 100:.1f}%",
                _format_duration(item.get("time_since_last_pick_seconds")),
                "yes" if bool(item.get("starvation_risk_flag")) else "no",
            )
        console.print(pool_table)
    return 0
