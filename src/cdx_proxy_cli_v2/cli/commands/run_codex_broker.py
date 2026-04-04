from __future__ import annotations

import argparse

from cdx_proxy_cli_v2.runtime.codex_broker import run_broker


def handle_run_codex_broker(args: argparse.Namespace) -> int:
    return run_broker(
        [
            "--cwd",
            args.cwd,
            "--socket-path",
            args.socket_path,
        ]
    )
