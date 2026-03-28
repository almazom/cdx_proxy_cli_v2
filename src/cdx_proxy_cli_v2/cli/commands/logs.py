from __future__ import annotations

import argparse
import sys

from cdx_proxy_cli_v2.runtime.service import tail_service_logs

from cdx_proxy_cli_v2.cli.shared import _settings_from_args


def handle_logs(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    lines = tail_service_logs(settings.auth_dir, lines=max(1, int(args.lines)))
    if not lines:
        print("No logs found", file=sys.stderr)
        return 0
    for line in lines:
        print(line)
    return 0
