from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from cdx_proxy_cli_v2.config.settings import Settings
from cdx_proxy_cli_v2.runtime.service import service_status

from cdx_proxy_cli_v2.cli.shared import _settings_from_args


def handle_status(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    payload = service_status(settings)

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
    Console().print(table)
    return 0
