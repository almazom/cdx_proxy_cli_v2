from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from cdx_proxy_cli_v2.cli.limits_view import (
    NO_LIMITS_SNAPSHOT_MESSAGE,
    _load_limits_history,
    _render_limits_history,
    _render_limits_snapshot,
)
from cdx_proxy_cli_v2.observability.limits_history import (
    latest_limits_path,
    limits_history_path,
    read_latest_limits_snapshot,
)

from cdx_proxy_cli_v2.cli.shared import _settings_from_args


def handle_limits(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    snapshot = read_latest_limits_snapshot(settings.auth_dir)
    history = _load_limits_history(
        settings.auth_dir, tail=max(0, int(getattr(args, "tail", 0)))
    )

    if bool(getattr(args, "json", False)):
        payload: Dict[str, Any] = {
            "snapshot": snapshot or None,
            "history": history,
            "files": {
                "latest": str(latest_limits_path(settings.auth_dir)),
                "history": str(limits_history_path(settings.auth_dir)),
            },
        }
        if not snapshot and not history:
            payload["error"] = NO_LIMITS_SNAPSHOT_MESSAGE
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not snapshot and not history:
        print(NO_LIMITS_SNAPSHOT_MESSAGE, file=sys.stderr)
        return 1

    if snapshot:
        _render_limits_snapshot(snapshot)
        print(f"Latest file: {latest_limits_path(settings.auth_dir)}")
    if history:
        _render_limits_history(history)
        print(f"History file: {limits_history_path(settings.auth_dir)}")
    return 0
