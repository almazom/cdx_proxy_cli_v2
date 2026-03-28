from __future__ import annotations

import argparse
import sys

from cdx_proxy_cli_v2.observability.tui import run_trace_tui
from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.runtime.service import service_status
from cdx_proxy_cli_v2.runtime.singleton import (
    SingletonLockError,
    is_expected_trace_process,
    singleton_lock,
    trace_pid_path,
)

from cdx_proxy_cli_v2.cli.shared import (
    _management_headers,
    _settings_from_args,
)


def handle_trace(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)

    pid_path = trace_pid_path(settings.auth_dir)
    replace_existing = bool(getattr(args, "replace", False))

    try:
        with singleton_lock(
            pid_path,
            name="cdx trace",
            kill_existing=replace_existing,
            process_matches=lambda pid: is_expected_trace_process(pid, settings.auth_dir),
        ) as (
            killed_existing,
            previous_pid,
        ):
            if killed_existing and previous_pid:
                print(f"Replaced existing cdx trace (PID {previous_pid})", file=sys.stderr)

            status_payload = service_status(settings)
            if not status_payload.get("healthy"):
                print("Proxy not running. Run `cdx proxy` first.", file=sys.stderr)
                return 1
            base_url = str(status_payload.get("base_url") or settings.base_url)
            headers = _management_headers(settings)
            upstream_base_url = None
            log_request_preview = None
            try:
                debug = fetch_json(
                    base_url=base_url,
                    path="/debug",
                    headers=headers,
                    timeout=2.0,
                )
                upstream_base_url = debug.get("upstream_base_url")
                if "log_request_preview" in debug:
                    log_request_preview = bool(debug.get("log_request_preview"))
            except Exception:
                print("Proxy not running. Run `cdx proxy` first.", file=sys.stderr)
                return 1
            try:
                run_trace_tui(
                    base_url=base_url,
                    upstream_base_url=str(upstream_base_url) if upstream_base_url else None,
                    log_request_preview=log_request_preview,
                    window=max(1, int(args.limit)),
                    interval=max(0.1, float(args.interval)),
                    limit=max(0, int(args.limit)),
                    extra_headers=headers,
                )
            except KeyboardInterrupt:
                return 0
    except SingletonLockError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
