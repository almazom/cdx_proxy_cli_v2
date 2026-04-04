from __future__ import annotations

import argparse
import json
import os

from cdx_proxy_cli_v2.cli.shared import _settings_from_args
from cdx_proxy_cli_v2.runtime.codex_runtime import (
    codex_runtime_status,
    ensure_codex_runtime,
    stop_codex_runtime,
)


def handle_codex_runtime_ensure(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    payload = ensure_codex_runtime(settings, args.cwd)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(f"workspace_root={payload['workspace_root']}")
        print(f"state={payload['state']}")
        print(f"endpoint={payload['endpoint']}")
        print(f"pid={payload['pid']}")
        print(f"log_file={payload['log_file']}")
        print(f"started={payload['started']}")
        print(f"reused={payload['reused']}")
    return 0


def handle_codex_runtime_status(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    payload = codex_runtime_status(settings, args.cwd)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(f"workspace_root={payload['workspace_root']}")
        print(f"state={payload['state']}")
        print(f"endpoint={payload['endpoint'] or '-'}")
        print(f"pid={payload['pid']}")
        print(f"pid_running={payload['pid_running']}")
        print(f"healthy={payload['healthy']}")
        print(f"log_file={payload['log_file']}")
    return 0


def handle_codex_runtime_stop(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    stopped = stop_codex_runtime(settings, args.cwd)
    payload = {
        "workspace_root": str(PathLike(args.cwd)),
        "stopped": stopped,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print("stopped=yes" if stopped else "stopped=no")
    return 0


class PathLike(str):
    def __new__(cls, value: str):
        return super().__new__(cls, os.path.abspath(os.path.expanduser(value)))
