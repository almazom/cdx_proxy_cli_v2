from __future__ import annotations

import argparse

from cdx_proxy_cli_v2.proxy.server import run_proxy_server

from cdx_proxy_cli_v2.cli.shared import _settings_from_args


def handle_run_server(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    run_proxy_server(settings)
    return 0
