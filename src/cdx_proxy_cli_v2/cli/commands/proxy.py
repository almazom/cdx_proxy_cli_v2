from __future__ import annotations

import argparse
import sys

from cdx_proxy_cli_v2.runtime.service import start_service, stop_service

from cdx_proxy_cli_v2.cli.shared import (
    _proxy_eval_hint,
    _proxy_exports,
    _proxy_shell_setup,
    _settings_from_args,
)


def handle_proxy(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)

    # Handle --force: stop any existing proxy first
    if getattr(args, "force", False):
        stopped = stop_service(settings)
        if stopped and not bool(getattr(args, "quiet", False)):
            print("Stopped existing proxy (force mode)", file=sys.stderr)

    result = start_service(settings)
    exports = _proxy_exports(
        settings,
        base_url=result.base_url,
        host=result.host,
        port=result.port,
    )
    quiet = bool(getattr(args, "quiet", False))

    if bool(getattr(args, "print_env_only", False)):
        print(_proxy_shell_setup(exports))
        return 0

    if args.print_env:
        if not quiet:
            step = "started" if result.started else "already running"
            print(f"# proxy {step} on {result.base_url}", file=sys.stderr)
        print(_proxy_shell_setup(exports))
        return 0

    # Interactive output - status messages to stderr
    if not quiet:
        if result.started:
            print(f"Proxy started on {result.base_url}", file=sys.stderr)
        else:
            print(f"Proxy already running on {result.base_url}", file=sys.stderr)
        print(f"Auth dir: {settings.auth_dir}", file=sys.stderr)
        print(f"One-line shell setup: {_proxy_eval_hint(settings)}", file=sys.stderr)
        print("Next: run `cdx trace` or use `codex` in this shell", file=sys.stderr)
    return 0
