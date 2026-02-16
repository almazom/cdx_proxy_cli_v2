from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table

from cdx_proxy_cli_v2 import __version__
from cdx_proxy_cli_v2.observability.collective_dashboard import build_collective_payload, render_collective_dashboard
from cdx_proxy_cli_v2.proxy.server import run_proxy_server
from cdx_proxy_cli_v2.runtime.service import (
    service_status,
    start_service,
    stop_service,
    tail_service_logs,
)
from cdx_proxy_cli_v2.config.settings import Settings, build_settings, format_shell_exports
from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.observability.tui import run_trace_tui
from cdx_proxy_cli_v2.auth.store import extract_auth_fields, read_auth_json


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--auth-dir", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--upstream", default=None)
    parser.add_argument("--management-key", default=None)
    parser.add_argument("--trace-max", type=int, default=None)
    parser.add_argument("--allow-non-loopback", action="store_true", default=None)


def _settings_from_args(args: argparse.Namespace) -> Settings:
    return build_settings(
        auth_dir=getattr(args, "auth_dir", None),
        host=getattr(args, "host", None),
        port=getattr(args, "port", None),
        upstream=getattr(args, "upstream", None),
        management_key=getattr(args, "management_key", None),
        allow_non_loopback=getattr(args, "allow_non_loopback", None),
        trace_max=getattr(args, "trace_max", None),
    )


def _proxy_exports(settings: Settings, *, base_url: str, host: str, port: int) -> Dict[str, str]:
    return {
        "OPENAI_BASE_URL": base_url,
        "OPENAI_API_BASE": base_url,
        "CLIPROXY_AUTH_DIR": settings.auth_dir,
        "CLIPROXY_ENV_FILE": str(settings.env_path),
        "CLIPROXY_HOST": host,
        "CLIPROXY_PORT": str(port),
    }


def _management_headers(settings: Settings) -> Dict[str, str]:
    key = str(settings.management_key or "").strip()
    if not key:
        return {}
    return {"X-Management-Key": key}


def _proxy_eval_hint(settings: Settings) -> str:
    auth_dir = shlex.quote(settings.auth_dir)
    return f'eval "$(cdx2 proxy --auth-dir {auth_dir} --print-env-only)"'


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
    result = start_service(settings)
    exports = _proxy_exports(
        settings,
        base_url=result.base_url,
        host=result.host,
        port=result.port,
    )
    if bool(getattr(args, "print_env_only", False)):
        print(format_shell_exports(exports))
        return 0

    if args.print_env:
        step = "started" if result.started else "already running"
        print(f"# proxy {step} on {result.base_url}", file=sys.stderr)
        print(format_shell_exports(exports))
        return 0

    if result.started:
        print(f"Proxy started on {result.base_url}")
    else:
        print(f"Proxy already running on {result.base_url}")
    print(f"Auth dir: {settings.auth_dir}")
    print(f"One-line shell setup: {_proxy_eval_hint(settings)}")
    print("Next: run `cdx2 trace` or use `codex` in this shell")
    return 0


def handle_status(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    payload = service_status(settings)
    table = Table(title="cdx2 service status")
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


def _state_bucket(status: object) -> str:
    normalized = str(status or "UNKNOWN").upper()
    if normalized == "OK":
        return "whitelist"
    if normalized == "PROBATION":
        return "probation"
    if normalized == "COOLDOWN":
        return "cooldown"
    if normalized == "BLACKLIST":
        return "blacklist"
    return "unknown"


def handle_doctor(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    status_payload = service_status(settings)
    base_url = str(status_payload.get("base_url") or settings.base_url)
    healthy = bool(status_payload.get("healthy"))
    if not healthy:
        print("Proxy is not healthy/running. Start with `cdx2 proxy` first.", file=sys.stderr)
        return 1

    headers = _management_headers(settings)
    try:
        health_payload = fetch_json(
            base_url=base_url,
            path="/health?refresh=1",
            headers=headers,
            timeout=2.0,
        )
    except Exception as exc:
        print(f"Doctor failed to read /health: {exc}", file=sys.stderr)
        return 1

    accounts_raw = health_payload.get("accounts", [])
    accounts: List[Dict[str, Any]] = [item for item in accounts_raw if isinstance(item, dict)] if isinstance(accounts_raw, list) else []
    summary = {
        "whitelist": 0,
        "probation": 0,
        "cooldown": 0,
        "blacklist": 0,
        "unknown": 0,
        "total": len(accounts),
    }
    for item in accounts:
        bucket = _state_bucket(item.get("status"))
        summary[bucket] += 1

    payload: Dict[str, Any] = {
        "ok": True,
        "base_url": base_url,
        "policy": {
            "hard_fail_blacklist": [401, 403],
            "rate_limit_cooldown": 429,
            "probation_success_target": 2,
        },
        "summary": summary,
        "accounts": accounts,
    }
    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    table = Table(title="cdx2 doctor | auth rotation state")
    table.add_column("File")
    table.add_column("Status")
    table.add_column("Cooldown")
    table.add_column("Blacklist")
    table.add_column("Probation")
    table.add_column("Used")
    table.add_column("Errors")
    table.add_column("Reason")
    for item in sorted(accounts, key=lambda row: str(row.get("file") or "")):
        table.add_row(
            str(item.get("file") or "-"),
            str(item.get("status") or "UNKNOWN"),
            str(item.get("cooldown_seconds") or "-"),
            str(item.get("blacklist_seconds") or "-"),
            f"{item.get('probation_successes')}/{item.get('probation_target')}"
            if item.get("probation")
            else "-",
            str(item.get("used") or 0),
            str(item.get("errors") or 0),
            str(item.get("blacklist_reason") or "-"),
        )
    Console().print(table)
    print(
        "Summary: "
        f"white={summary['whitelist']} probation={summary['probation']} "
        f"cooldown={summary['cooldown']} black={summary['blacklist']} unknown={summary['unknown']}"
    )
    print("Policy: 401/403 -> blacklist, 429 -> exponential cooldown, re-entry via probation")
    return 0


def handle_stop(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    stopped = stop_service(settings)
    if stopped:
        print("Proxy stopped")
    else:
        print("Proxy is not running")
    return 0


def handle_trace(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    base_url = settings.base_url
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
        print("Proxy not running. Run `cdx2 proxy` first.", file=sys.stderr)
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
        print("No logs found")
        return 0
    for line in lines:
        print(line)
    return 0


def handle_all(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    _status_payload = service_status(settings)
    usage_base_url = os.environ.get("CLIPROXY_USAGE_BASE_URL") or "https://chatgpt.com/backend-api"
    current_access_token = os.environ.get("OPENAI_API_KEY")
    current_file = os.environ.get("CLIPROXY_CURRENT_AUTH_FILE")
    codex_access_token, codex_email, codex_account_id = _load_codex_auth_identity()
    if not current_access_token:
        current_access_token = codex_access_token

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="cdx proxy cli v2",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    proxy_parser = sub.add_parser(
        "proxy",
        help="start or reuse proxy service",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Quick one-liners:\n"
            "  start only:\n"
            "    cdx2 proxy --auth-dir ~/.codex/_auths\n"
            "  safe env export into current shell:\n"
            "    eval \"$(cdx2 proxy --auth-dir ~/.codex/_auths --print-env-only)\"\n"
            "  full setup + trace in one line:\n"
            "    eval \"$(cdx2 proxy --auth-dir ~/.codex/_auths --print-env-only)\" && cdx2 trace --auth-dir ~/.codex/_auths --limit 20\n"
            "  then open trace:\n"
            "    cdx2 trace --auth-dir ~/.codex/_auths --limit 20\n"
        ),
    )
    _add_runtime_options(proxy_parser)
    proxy_mode_group = proxy_parser.add_mutually_exclusive_group()
    proxy_mode_group.add_argument("--print-env", action="store_true", help="print shell exports (with status line to stderr)")
    proxy_mode_group.add_argument(
        "--print-env-only",
        action="store_true",
        help="print only `export ...` lines (safe for eval/source)",
    )
    proxy_parser.set_defaults(handler=handle_proxy)

    status_parser = sub.add_parser("status", help="service status")
    _add_runtime_options(status_parser)
    status_parser.set_defaults(handler=handle_status)

    doctor_parser = sub.add_parser("doctor", help="rotation doctor (white/black/probation)")
    _add_runtime_options(doctor_parser)
    doctor_parser.add_argument("--json", action="store_true")
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

    all_parser = sub.add_parser("all", help="show all keys cards dashboard (v1 style)")
    _add_runtime_options(all_parser)
    all_parser.add_argument("--warn-at", type=int, default=70, help="warn threshold in used percent")
    all_parser.add_argument("--cooldown-at", type=int, default=90, help="cooldown threshold in used percent")
    all_parser.add_argument("--timeout", type=int, default=8, help="usage endpoint request timeout seconds")
    all_parser.add_argument(
        "--only",
        choices=["both", "5h", "weekly"],
        default="both",
        help="window filter for limits dashboard",
    )
    all_parser.add_argument("--json", action="store_true", help="machine-readable output for agents/automation")
    all_parser.set_defaults(handler=handle_all)

    run_server_parser = sub.add_parser("run-server", help=argparse.SUPPRESS)
    _add_runtime_options(run_server_parser)
    run_server_parser.set_defaults(handler=handle_run_server)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
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
