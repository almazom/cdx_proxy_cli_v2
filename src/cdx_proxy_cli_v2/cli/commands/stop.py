from __future__ import annotations

import argparse
import sys

from cdx_proxy_cli_v2.runtime.service import stop_service

from cdx_proxy_cli_v2.cli.shared import _settings_from_args


def handle_stop(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    stopped = stop_service(settings)
    quiet = bool(getattr(args, "quiet", False))
    if not quiet:
        if stopped:
            print("Proxy stopped", file=sys.stderr)
        else:
            print("Proxy is not running", file=sys.stderr)
    return 0
