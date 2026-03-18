from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from rich.console import Console
from rich.table import Table

from cdx_proxy_cli_v2 import __version__
from cdx_proxy_cli_v2.cli import doctor_view as _doctor_view
from cdx_proxy_cli_v2.cli.doctor_view import (
    _doctor_payload,
    _extract_accounts,
    _render_doctor_table,
    _render_probe_results,
)
from cdx_proxy_cli_v2.cli.fs import _atomic_write_json, _get_codex_home
from cdx_proxy_cli_v2.cli.limits_view import (
    NO_LIMITS_SNAPSHOT_MESSAGE,
    _load_limits_history,
    _render_limits_history,
    _render_limits_snapshot,
)
from cdx_proxy_cli_v2.observability.collective_dashboard import (
    build_collective_payload,
    build_collective_payload_from_accounts,
    render_collective_dashboard,
)
from cdx_proxy_cli_v2.observability.limits_history import (
    latest_limits_path,
    limits_history_path,
    read_latest_limits_snapshot,
)
from cdx_proxy_cli_v2.proxy.server import run_proxy_server
from cdx_proxy_cli_v2.runtime.service import (
    service_status,
    start_service,
    stop_service,
    tail_service_logs,
)
from cdx_proxy_cli_v2.config.settings import (
    Settings,
    build_settings,
    format_shell_exports,
)
from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.observability.tui import run_trace_tui
from cdx_proxy_cli_v2.auth.store import extract_auth_fields, read_auth_json

_state_bucket = _doctor_view._state_bucket

DOCTOR_HEALTH_TIMEOUT_SECONDS = 8.0
ROTATE_HEALTH_TIMEOUT_SECONDS = 2.5
DOCTOR_POLICY = {
    "hard_fail_blacklist": [401, 403],
    "rate_limit_cooldown": 429,
    "probation_success_target": 2,
}


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--auth-dir", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--upstream", default=None)
    parser.add_argument("--management-key", default=None)
    parser.add_argument("--trace-max", type=int, default=None)
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=None,
        help="timeout seconds for /responses endpoints",
    )
    parser.add_argument(
        "--limit-min-remaining-percent",
        type=float,
        default=None,
        help="preemptive limit guardrail; quarantine keys when a limit window has less remaining percent than this",
    )
    parser.add_argument(
        "--max-in-flight-requests",
        type=int,
        default=None,
        help="local overload guard: max concurrent proxied requests (0 disables)",
    )
    parser.add_argument(
        "--max-pending-requests",
        type=int,
        default=None,
        help="local overload guard: max waiting requests once in-flight is full",
    )
    parser.add_argument("--allow-non-loopback", action="store_true", default=None)
    parser.set_defaults(auto_reset_on_single_key=None)
    parser.add_argument(
        "--auto-reset-on-single-key",
        dest="auto_reset_on_single_key",
        action="store_true",
        help="auto-reset blacklist/probation keys after a sustained one-key trace streak",
    )
    parser.add_argument(
        "--no-auto-reset-on-single-key",
        dest="auto_reset_on_single_key",
        action="store_false",
        help="disable one-key starvation auto-reset even if enabled in env",
    )
    parser.add_argument(
        "--auto-reset-streak",
        type=int,
        default=None,
        help="recent same-key trace events required before auto-reset",
    )
    parser.add_argument(
        "--auto-reset-cooldown",
        type=int,
        default=None,
        help="minimum seconds between automatic recovery resets",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress non-error output",
    )


def _settings_from_args(args: argparse.Namespace) -> Settings:
    return build_settings(
        auth_dir=getattr(args, "auth_dir", None),
        host=getattr(args, "host", None),
        port=getattr(args, "port", None),
        upstream=getattr(args, "upstream", None),
        management_key=getattr(args, "management_key", None),
        allow_non_loopback=getattr(args, "allow_non_loopback", None),
        trace_max=getattr(args, "trace_max", None),
        request_timeout=getattr(args, "request_timeout", None),
        limit_min_remaining_percent=getattr(args, "limit_min_remaining_percent", None),
        max_in_flight_requests=getattr(args, "max_in_flight_requests", None),
        max_pending_requests=getattr(args, "max_pending_requests", None),
        auto_reset_on_single_key=getattr(args, "auto_reset_on_single_key", None),
        auto_reset_streak=getattr(args, "auto_reset_streak", None),
        auto_reset_cooldown=getattr(args, "auto_reset_cooldown", None),
    )


def _proxy_exports(
    settings: Settings, *, base_url: str, host: str, port: int
) -> Dict[str, str]:
    return {
        "CLIPROXY_BASE_URL": base_url,
        "OPENAI_API_BASE": base_url,
        "CLIPROXY_AUTH_DIR": settings.auth_dir,
        "CLIPROXY_ENV_FILE": str(settings.env_path),
        "CLIPROXY_HOST": host,
        "CLIPROXY_PORT": str(port),
    }


def _proxy_shell_setup(exports: Dict[str, str]) -> str:
    base_url = exports["CLIPROXY_BASE_URL"]
    return (
        f"{format_shell_exports(exports)}\n"
        "codex() {\n"
        '  env -u OPENAI_BASE_URL -u OPENAI_API_BASE command codex \\\n'
        f'    -c "openai_base_url=\\"{base_url}\\"" "$@"\n'
        "}\n"
    )


def _management_headers(settings: Settings) -> Dict[str, str]:
    key = str(settings.management_key or "").strip()
    if not key:
        return {}
    return {"X-Management-Key": key}


def _proxy_eval_hint(settings: Settings) -> str:
    auth_dir = shlex.quote(settings.auth_dir)
    return f'eval "$(cdx proxy --auth-dir {auth_dir} --print-env-only)"'


def _load_codex_auth_identity() -> tuple[Optional[str], Optional[str], Optional[str]]:
    code_home = str(os.environ.get("CODEX_HOME") or "").strip()
    if code_home:
        codex_home = Path(os.path.expanduser(code_home))
    else:
        home_dir = Path(os.path.expanduser(str(os.environ.get("HOME") or "~")))
        codex_home = home_dir / ".codex"
    for candidate in ("auth.json", ".auth.json"):
        auth_path = codex_home / candidate
        if not auth_path.exists():
            continue
        raw, error = read_auth_json(auth_path)
        if error or raw is None:
            continue
        token, email, account_id = extract_auth_fields(raw)
        return (token or None), email, account_id
    return None, None, None


def handle_proxy(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)

    # Handle --force: stop any existing proxy first
    if getattr(args, "force", False):
        from cdx_proxy_cli_v2.runtime.service import stop_service

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


def _healthy_base_url_or_none(settings: Settings) -> Optional[str]:
    status_payload = service_status(settings)
    base_url = str(status_payload.get("base_url") or settings.base_url)
    healthy = bool(status_payload.get("healthy"))
    if not healthy:
        print(
            "Proxy is not healthy/running. Start with `cdx proxy` first.",
            file=sys.stderr,
        )
        return None
    return base_url


def _fetch_health_accounts(
    *, base_url: str, headers: Dict[str, str], timeout: float
) -> List[Dict[str, Any]]:
    payload = fetch_json(
        base_url=base_url,
        path="/health?refresh=1",
        headers=headers,
        timeout=timeout,
    )
    return _extract_accounts(payload)


def _rotation_accounts(
    *, settings: Settings, base_url: str, headers: Dict[str, str]
) -> List[Dict[str, Any]]:
    last_error: Optional[Exception] = None
    for path in ("/health", "/trace?limit=1"):
        try:
            payload = fetch_json(
                base_url=base_url,
                path=path,
                headers=headers,
                timeout=ROTATE_HEALTH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            last_error = exc
            continue
        if path.startswith("/trace"):
            limits = payload.get("limits")
            if isinstance(limits, dict):
                accounts = _extract_accounts(limits)
                if accounts:
                    return accounts
            continue
        accounts = _extract_accounts(payload)
        if accounts:
            return accounts

    snapshot = read_latest_limits_snapshot(settings.auth_dir)
    accounts = _extract_accounts(snapshot)
    if accounts:
        return accounts
    if last_error is not None:
        raise RuntimeError(str(last_error))
    raise RuntimeError("no auth state available")


def handle_doctor(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    base_url = _healthy_base_url_or_none(settings)
    if base_url is None:
        return 1

    headers = _management_headers(settings)

    # Handle --probe flag: proactively test auth keys
    if getattr(args, "probe", False):
        timeout = getattr(args, "probe_timeout", 10)
        timeout = max(1, min(30, timeout))

        try:
            probe_payload = fetch_json(
                base_url=base_url,
                path=f"/probe?timeout={timeout}",
                method="POST",
                headers=headers,
                timeout=float(timeout) + 5.0,  # Extra buffer for processing
            )
        except Exception as exc:
            print(f"Probe failed: {exc}", file=sys.stderr)
            return 1

        _render_probe_results(probe_payload, json_mode=bool(args.json))

        # Include probe results in JSON output
        if bool(args.json):
            try:
                accounts = _fetch_health_accounts(
                    base_url=base_url,
                    headers=headers,
                    timeout=DOCTOR_HEALTH_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                print(
                    f"Doctor failed to read /health after probe: {exc}", file=sys.stderr
                )
                return 1

            output = _doctor_payload(
                base_url=base_url,
                accounts=accounts,
                policy=DOCTOR_POLICY,
                probe=probe_payload,
            )
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

    # Regular doctor flow (always fetch health)
    try:
        accounts = _fetch_health_accounts(
            base_url=base_url,
            headers=headers,
            timeout=DOCTOR_HEALTH_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        print(f"Doctor failed to read /health: {exc}", file=sys.stderr)
        return 1

    payload = _doctor_payload(
        base_url=base_url, accounts=accounts, policy=DOCTOR_POLICY
    )
    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    _render_doctor_table(accounts, payload["summary"])
    return 0


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


def handle_trace(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    # Get actual running proxy endpoint from state file, not default settings
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
    return 0


def handle_logs(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    lines = tail_service_logs(settings.auth_dir, lines=max(1, int(args.lines)))
    if not lines:
        print("No logs found", file=sys.stderr)
        return 0
    # Log content goes to stdout (data output)
    for line in lines:
        print(line)
    return 0


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


def handle_all(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    status_payload = service_status(settings)
    usage_base_url = (
        os.environ.get("CLIPROXY_USAGE_BASE_URL") or "https://chatgpt.com/backend-api"
    )
    current_access_token = os.environ.get("OPENAI_API_KEY")
    current_file = os.environ.get("CLIPROXY_CURRENT_AUTH_FILE")
    codex_access_token, codex_email, codex_account_id = _load_codex_auth_identity()
    if not current_access_token:
        current_access_token = codex_access_token

    payload = None
    if bool(status_payload.get("healthy")):
        base_url = str(status_payload.get("base_url") or settings.base_url)
        try:
            accounts = _fetch_health_accounts(
                base_url=base_url,
                headers=_management_headers(settings),
                timeout=DOCTOR_HEALTH_TIMEOUT_SECONDS,
            )
            payload = build_collective_payload_from_accounts(
                accounts=accounts,
                warn_at=int(args.warn_at),
                cooldown_at=int(args.cooldown_at),
                only=str(args.only),
                current_access_token=current_access_token,
                current_file=current_file,
                current_email=codex_email,
                current_account_id=codex_account_id,
            )
        except Exception:
            payload = None

    if payload is None:
        payload = build_collective_payload(
            auths_dir=settings.auth_dir,
            base_url=usage_base_url,
            warn_at=int(args.warn_at),
            cooldown_at=int(args.cooldown_at),
            timeout=int(args.timeout),
            only=str(args.only),
            current_access_token=current_access_token,
            current_file=current_file,
            current_email=codex_email,
            current_account_id=codex_account_id,
        )
    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    render_collective_dashboard(payload)
    return 0


def handle_run_server(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    run_proxy_server(settings)
    return 0


def _build_reset_path(*, name: Optional[str], state: Optional[str]) -> str:
    params: Dict[str, str] = {}
    if name:
        params["name"] = str(name)
    if state:
        params["state"] = str(state)

    query = urlencode(params)
    if not query:
        return "/reset"
    return f"/reset?{query}"


def handle_reset(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    base_url = _healthy_base_url_or_none(settings)
    if base_url is None:
        return 1

    headers = _management_headers(settings)
    path = _build_reset_path(
        name=getattr(args, "name", None),
        state=getattr(args, "state", None),
    )

    try:
        result = fetch_json(
            base_url=base_url,
            path=path,
            method="POST",
            headers=headers,
            timeout=5.0,
        )
    except Exception as exc:
        print(f"Reset failed: {exc}", file=sys.stderr)
        return 1

    count = result.get("reset", 0)
    filter_info = result.get("filter", {})

    if bool(getattr(args, "json", False)):
        print(json.dumps(result, indent=2))
        return 0

    # Print summary
    filter_str = ""
    if filter_info.get("name"):
        filter_str = f" (name={filter_info['name']})"
    elif filter_info.get("state"):
        filter_str = f" (state={filter_info['state']})"

    print(f"Reset {count} auth key(s){filter_str}")
    return 0


def handle_rotate(args: argparse.Namespace) -> int:
    """Rotate active auth key for codex CLI.

    Finds a healthy auth from the _auths directory and copies it to
    the active auth.json location for use by the codex CLI.
    """
    settings = _settings_from_args(args)
    base_url = _healthy_base_url_or_none(settings)
    if base_url is None:
        return 1

    headers = _management_headers(settings)
    try:
        accounts = _rotation_accounts(settings=settings, base_url=base_url, headers=headers)
    except Exception as exc:
        print(f"Failed to fetch health status: {exc}", file=sys.stderr)
        return 1

    # Filter for currently usable auths from cached runtime/limits state.
    healthy_auths = [
        acc
        for acc in accounts
        if (
            bool(acc.get("eligible_now"))
            or str(acc.get("status", "")).upper() in {"OK", "WARN"}
        )
    ]

    if not healthy_auths:
        print("Error: No healthy auth keys available.", file=sys.stderr)
        print(
            "All keys are in cooldown, blacklist, or probation state.", file=sys.stderr
        )
        print("Run `cdx doctor` to see current auth states.", file=sys.stderr)
        return 1

    # Sort by used count (ascending) to pick least-used, then by file name for stability
    healthy_auths.sort(
        key=lambda a: (int(a.get("used") or 0), str(a.get("file") or ""))
    )
    selected = healthy_auths[0]

    selected_file = str(selected.get("file") or "")
    selected_email = str(selected.get("email") or selected.get("account") or "")
    selected_used = int(selected.get("used") or 0)

    # Resolve the source auth file path
    auth_dir_path = Path(settings.auth_dir).expanduser().resolve()
    source_path = auth_dir_path / selected_file

    # Determine destination path
    codex_home = _get_codex_home()
    dest_path = codex_home / "auth.json"

    dry_run = bool(getattr(args, "dry_run", False))
    json_output = bool(getattr(args, "json", False))

    # Handle dry-run before file system operations
    if dry_run:
        if json_output:
            output = {
                "dry_run": True,
                "selected": {
                    "file": selected_file,
                    "email": selected_email,
                    "used": selected_used,
                },
                "source": str(source_path),
                "destination": str(dest_path),
            }
            print(json.dumps(output, indent=2))
        else:
            print("Dry run: Would rotate to auth key")
            print(f"  File: {selected_file}")
            if selected_email:
                print(f"  Email: {selected_email}")
            print(f"  Used count: {selected_used}")
            print(f"  Source: {source_path}")
            print(f"  Destination: {dest_path}")
        return 0

    # Validate source path is within auth directory (prevent path traversal)
    try:
        if not source_path.resolve().is_relative_to(auth_dir_path):
            print(f"Error: Invalid auth file path: {selected_file}", file=sys.stderr)
            return 1
    except OSError:
        print(f"Error: Cannot resolve auth file path: {selected_file}", file=sys.stderr)
        return 1

    if not source_path.exists():
        print(f"Error: Auth file not found: {source_path}", file=sys.stderr)
        return 1

    # Read the source auth file
    raw, error = read_auth_json(source_path)
    if error or raw is None:
        print(f"Error: Failed to read auth file: {error}", file=sys.stderr)
        return 1

    # Perform the rotation (atomic write)
    try:
        _atomic_write_json(dest_path, raw)
    except Exception as exc:
        print(f"Error: Failed to write auth file: {exc}", file=sys.stderr)
        return 1

    if json_output:
        output = {
            "success": True,
            "selected": {
                "file": selected_file,
                "email": selected_email,
                "used": selected_used,
            },
            "destination": str(dest_path),
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Rotated to auth key: {selected_file}")
        if selected_email:
            print(f"  Email: {selected_email}")
        print(f"  Used count: {selected_used}")
        print(f"  Written to: {dest_path}")

    return 0


def handle_migrate(args: argparse.Namespace) -> int:
    """Migrate from cdx_proxy_cli v1 to v2."""
    v1_dir = getattr(args, "v1_auth_dir", None)
    dry_run = bool(getattr(args, "dry_run", False))

    if not v1_dir:
        v1_dir = os.path.expanduser("~/.codex/_auths")

    v1_path = Path(v1_dir)
    if not v1_path.exists():
        print(f"Error: V1 auth directory not found: {v1_dir}", file=sys.stderr)
        return 1

    # V1 file names
    v1_files = [
        "rr_proxy.pid",
        "rr_proxy.state.json",
        "rr_proxy.log",
        "rr_proxy.events.jsonl",
    ]
    # V2 file names
    v2_files = [
        "rr_proxy_v2.pid",
        "rr_proxy_v2.state.json",
        "rr_proxy_v2.log",
        "rr_proxy_v2.events.jsonl",
    ]

    print(f"Scanning V1 directory: {v1_dir}")
    print("-" * 50)

    migrated = 0
    for v1_name, v2_name in zip(v1_files, v2_files):
        v1_file = v1_path / v1_name
        v2_file = v1_path / v2_name

        if v1_file.exists():
            if dry_run:
                print(f"Would migrate: {v1_name} → {v2_name}")
            else:
                # Migrate file
                content = v1_file.read_text(encoding="utf-8")

                # For state file, add schema version
                if v1_name == "rr_proxy.state.json":
                    try:
                        state_data = json.loads(content)
                        state_data["$schema_version"] = "1.0.0"
                        content = json.dumps(state_data, indent=2)
                    except json.JSONDecodeError:
                        pass

                v2_file.write_text(content, encoding="utf-8")
                print(f"Migrated: {v1_name} → {v2_name}")
            migrated += 1
        else:
            print(f"Skipped (not found): {v1_name}")

    print("-" * 50)
    print(f"Migrated: {migrated} files")

    if dry_run:
        print("\nThis was a dry run. Remove --dry-run to actually migrate.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="cdx proxy cli v2",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    proxy_parser = sub.add_parser(
        "proxy",
        help="start or reuse proxy service",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Quick one-liners:\n"
            "  start only:\n"
            "    cdx proxy --auth-dir ~/.codex/_auths\n"
            "  safe env export into current shell:\n"
            '    eval "$(cdx proxy --auth-dir ~/.codex/_auths --print-env-only)"\n'
            "  full setup + trace in one line:\n"
            '    eval "$(cdx proxy --auth-dir ~/.codex/_auths --print-env-only)" && cdx trace --auth-dir ~/.codex/_auths --limit 20\n'
            "  then open trace:\n"
            "    cdx trace --auth-dir ~/.codex/_auths --limit 20\n"
        ),
    )
    _add_runtime_options(proxy_parser)
    proxy_parser.add_argument(
        "--force",
        action="store_true",
        help="force restart: stop any existing proxy before starting",
    )
    proxy_mode_group = proxy_parser.add_mutually_exclusive_group()
    proxy_mode_group.add_argument(
        "--print-env",
        action="store_true",
        help="print shell exports (with status line to stderr)",
    )
    proxy_mode_group.add_argument(
        "--print-env-only",
        action="store_true",
        help="print only `export ...` lines (safe for eval/source)",
    )
    proxy_parser.set_defaults(handler=handle_proxy)

    status_parser = sub.add_parser("status", help="service status")
    _add_runtime_options(status_parser)
    status_parser.add_argument(
        "--json", action="store_true", help="JSON output for scripting"
    )
    status_parser.set_defaults(handler=handle_status)

    doctor_parser = sub.add_parser(
        "doctor", help="rotation doctor (white/black/probation)"
    )
    _add_runtime_options(doctor_parser)
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.add_argument(
        "--probe",
        action="store_true",
        help="proactively test auth keys via HTTP requests",
    )
    doctor_parser.add_argument(
        "--fix", dest="probe", action="store_true", help="alias for --probe"
    )
    doctor_parser.add_argument(
        "--repair", dest="probe", action="store_true", help="alias for --probe"
    )
    doctor_parser.add_argument(
        "--probe-timeout",
        type=int,
        default=10,
        help="per-key timeout in seconds (default: 10, max: 30)",
    )
    doctor_parser.set_defaults(handler=handle_doctor)

    stop_parser = sub.add_parser("stop", help="stop proxy service")
    _add_runtime_options(stop_parser)
    stop_parser.set_defaults(handler=handle_stop)

    trace_parser = sub.add_parser("trace", help="open trace tui")
    _add_runtime_options(trace_parser)
    trace_parser.add_argument("--interval", type=float, default=1.0)
    trace_parser.add_argument("--limit", type=int, default=0)
    trace_parser.set_defaults(handler=handle_trace)

    logs_parser = sub.add_parser("logs", help="tail service logs")
    _add_runtime_options(logs_parser)
    logs_parser.add_argument("--lines", type=int, default=120)
    logs_parser.set_defaults(handler=handle_logs)

    limits_parser = sub.add_parser(
        "limits", help="show persisted limits snapshot and recent history"
    )
    _add_runtime_options(limits_parser)
    limits_parser.add_argument(
        "--tail",
        type=int,
        default=0,
        help="show the latest N persisted history entries from rr_proxy_v2.limits.jsonl",
    )
    limits_parser.add_argument(
        "--json", action="store_true", help="JSON output for scripting"
    )
    limits_parser.set_defaults(handler=handle_limits)

    migrate_parser = sub.add_parser(
        "migrate", help="migrate from cdx_proxy_cli v1 to v2"
    )
    migrate_parser.add_argument(
        "--v1-auth-dir",
        dest="v1_auth_dir",
        default=None,
        help="V1 auth directory (default: ~/.codex/_auths)",
    )
    migrate_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    migrate_parser.set_defaults(handler=handle_migrate)

    reset_parser = sub.add_parser("reset", help="reset auth key(s) to healthy state")
    _add_runtime_options(reset_parser)
    reset_parser.add_argument(
        "--name", default=None, help="reset specific auth file by name"
    )
    reset_parser.add_argument(
        "--state",
        choices=["blacklist", "cooldown", "probation"],
        default=None,
        help="reset only keys in this state",
    )
    reset_parser.add_argument(
        "--json", action="store_true", help="JSON output for scripting"
    )
    reset_parser.set_defaults(handler=handle_reset)

    rotate_parser = sub.add_parser(
        "rotate", help="rotate active auth key for codex CLI"
    )
    _add_runtime_options(rotate_parser)
    rotate_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="show what would be rotated without making changes",
    )
    rotate_parser.add_argument(
        "--json", action="store_true", help="JSON output for scripting"
    )
    rotate_parser.set_defaults(handler=handle_rotate)

    all_parser = sub.add_parser("all", help="show all keys cards dashboard (v1 style)")
    _add_runtime_options(all_parser)
    all_parser.add_argument(
        "--warn-at", type=int, default=70, help="warn threshold in used percent"
    )
    all_parser.add_argument(
        "--cooldown-at", type=int, default=90, help="cooldown threshold in used percent"
    )
    all_parser.add_argument(
        "--timeout", type=int, default=8, help="usage endpoint request timeout seconds"
    )
    all_parser.add_argument(
        "--only",
        choices=["both", "5h", "weekly"],
        default="both",
        help="window filter for limits dashboard",
    )
    all_parser.add_argument(
        "--json",
        action="store_true",
        help="machine-readable output for agents/automation",
    )
    all_parser.set_defaults(handler=handle_all)

    run_server_parser = sub.add_parser("run-server", help=argparse.SUPPRESS)
    _add_runtime_options(run_server_parser)
    run_server_parser.set_defaults(handler=handle_run_server)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for cdx CLI.

    Exit codes:
        0: Success
        1: Runtime error (service not running, network error)
        2: User error (invalid arguments, configuration error)
        130: Interrupted (Ctrl+C)
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return int(handler(args))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
