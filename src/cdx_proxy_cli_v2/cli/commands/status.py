from __future__ import annotations

import argparse
import json

from rich.console import Console
from rich.table import Table

from cdx_proxy_cli_v2.runtime.service import service_status

from cdx_proxy_cli_v2.cli.shared import _settings_from_args


def handle_status(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    payload = service_status(settings)
    triage_summary = payload.get("triage_summary")
    if not isinstance(triage_summary, dict):
        triage_summary = None

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
    return 0
