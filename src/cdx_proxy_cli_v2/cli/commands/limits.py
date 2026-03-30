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
from cdx_proxy_cli_v2.runtime.service import service_status

from cdx_proxy_cli_v2.cli.shared import (
    ROTATE_HEALTH_TIMEOUT_SECONDS,
    _fetch_runtime_next_auth,
    _management_headers,
    _settings_from_args,
)


def _snapshot_with_live_next_auth(
    snapshot: Dict[str, Any],
    *,
    live_next_auth: Dict[str, Any] | None,
    proxy_healthy: bool,
) -> Dict[str, Any]:
    display_snapshot = dict(snapshot)
    if live_next_auth is None:
        display_snapshot["next_auth_file"] = None
        display_snapshot["next_auth_email"] = None
        display_snapshot["next_auth_source"] = (
            "proxy_unavailable" if not proxy_healthy else "runtime_unavailable"
        )
        return display_snapshot

    display_snapshot["next_auth_file"] = str(live_next_auth.get("file") or "").strip() or None
    display_snapshot["next_auth_email"] = (
        str(live_next_auth.get("email") or "").strip() or None
    )
    display_snapshot["next_auth_source"] = "runtime"
    return display_snapshot


def handle_limits(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    snapshot = read_latest_limits_snapshot(settings.auth_dir)
    history = _load_limits_history(
        settings.auth_dir, tail=max(0, int(getattr(args, "tail", 0)))
    )
    status_payload = service_status(settings)
    proxy_healthy = bool(status_payload.get("healthy"))
    live_next_auth: Dict[str, Any] | None = None
    live_next_auth_error: str | None = None

    if proxy_healthy:
        base_url = str(status_payload.get("base_url") or settings.base_url)
        try:
            live_next_auth = _fetch_runtime_next_auth(
                base_url=base_url,
                headers=_management_headers(settings),
                timeout=ROTATE_HEALTH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            live_next_auth_error = str(exc)

    display_snapshot = None
    if snapshot:
        display_snapshot = _snapshot_with_live_next_auth(
            snapshot,
            live_next_auth=live_next_auth,
            proxy_healthy=proxy_healthy,
        )

    if bool(getattr(args, "json", False)):
        payload: Dict[str, Any] = {
            "snapshot": display_snapshot or None,
            "history": history,
            "proxy_healthy": proxy_healthy,
            "live_next_auth": live_next_auth,
            "files": {
                "latest": str(latest_limits_path(settings.auth_dir)),
                "history": str(limits_history_path(settings.auth_dir)),
            },
        }
        if live_next_auth_error:
            payload["live_next_auth_error"] = live_next_auth_error
        if not snapshot and not history:
            payload["error"] = NO_LIMITS_SNAPSHOT_MESSAGE
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not snapshot and not history:
        print(NO_LIMITS_SNAPSHOT_MESSAGE, file=sys.stderr)
        return 1

    if display_snapshot:
        _render_limits_snapshot(display_snapshot)
        print(f"Latest file: {latest_limits_path(settings.auth_dir)}")
    if history:
        _render_limits_history(history)
        print(f"History file: {limits_history_path(settings.auth_dir)}")
    return 0
