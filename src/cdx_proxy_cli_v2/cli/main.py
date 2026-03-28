"""cdx proxy cli v2 — thin router.

Handler functions live in cli/commands/. Shared helpers live in cli/shared.py.
This module owns only argparse wiring and the main entry point.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from cdx_proxy_cli_v2 import __version__
from cdx_proxy_cli_v2.cli.commands import (
    handle_all,
    handle_doctor,
    handle_limits,
    handle_logs,
    handle_migrate,
    handle_proxy,
    handle_reset,
    handle_rotate,
    handle_run_server,
    handle_status,
    handle_stop,
    handle_trace,
)
from cdx_proxy_cli_v2.cli.shared import (  # noqa: F401 — re-exported for backward compat
    DOCTOR_HEALTH_TIMEOUT_SECONDS,
    DOCTOR_POLICY,
    ROTATE_HEALTH_TIMEOUT_SECONDS,
    _fetch_health_accounts,
    _healthy_base_url_or_none,
    _load_codex_auth_identity,
    _management_headers,
    _proxy_eval_hint,
    _proxy_exports,
    _proxy_shell_setup,
    _settings_from_args,
)
from cdx_proxy_cli_v2.runtime.service import service_status
from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.observability.collective_dashboard import (
    build_collective_payload,
    build_collective_payload_from_accounts,
)
from cdx_proxy_cli_v2.cli.doctor_view import _state_bucket  # noqa: F401
from cdx_proxy_cli_v2.config.settings import format_shell_exports  # noqa: F401


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="cdx proxy cli v2",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- proxy --
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

    # -- status --
    status_parser = sub.add_parser(
        "status",
        help="service status",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx status\n"
            "  cdx status --json\n"
        ),
    )
    _add_runtime_options(status_parser)
    status_parser.add_argument(
        "--json", action="store_true", help="JSON output for scripting"
    )
    status_parser.set_defaults(handler=handle_status)

    # -- doctor --
    doctor_parser = sub.add_parser(
        "doctor",
        help="rotation doctor (white/black/probation)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx doctor\n"
            "  cdx doctor --probe\n"
            "  cdx doctor --fix\n"
        ),
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

    # -- stop --
    stop_parser = sub.add_parser(
        "stop",
        help="stop proxy service",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx stop\n"
        ),
    )
    _add_runtime_options(stop_parser)
    stop_parser.set_defaults(handler=handle_stop)

    # -- trace --
    trace_parser = sub.add_parser(
        "trace",
        help="open trace tui",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx trace\n"
            "  cdx trace --replace\n"
            "  cdx trace --limit 20\n"
        ),
    )
    _add_runtime_options(trace_parser)
    trace_parser.add_argument("--interval", type=float, default=1.0)
    trace_parser.add_argument("--limit", type=int, default=0)
    trace_parser.add_argument(
        "--replace",
        action="store_true",
        help="replace any existing cdx trace process",
    )
    trace_parser.add_argument(
        "--force",
        dest="replace",
        action="store_true",
        help=argparse.SUPPRESS,  # hidden alias for --replace
    )
    trace_parser.set_defaults(handler=handle_trace)

    # -- logs --
    logs_parser = sub.add_parser(
        "logs",
        help="tail service logs",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx logs\n"
            "  cdx logs --lines 50\n"
        ),
    )
    _add_runtime_options(logs_parser)
    logs_parser.add_argument("--lines", type=int, default=120)
    logs_parser.set_defaults(handler=handle_logs)

    # -- limits --
    limits_parser = sub.add_parser(
        "limits",
        help="show persisted limits snapshot and recent history",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx limits\n"
            "  cdx limits --tail 10\n"
            "  cdx limits --json\n"
        ),
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

    # -- migrate --
    migrate_parser = sub.add_parser(
        "migrate",
        help="migrate from cdx_proxy_cli v1 to v2",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx migrate\n"
            "  cdx migrate --dry-run\n"
        ),
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

    # -- reset --
    reset_parser = sub.add_parser(
        "reset",
        help="reset auth key(s) to healthy state",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx reset\n"
            "  cdx reset --state blacklist\n"
            "  cdx reset --name auth_001.json\n"
        ),
    )
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

    # -- rotate --
    rotate_parser = sub.add_parser(
        "rotate",
        help="rotate active auth key for codex CLI",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx rotate\n"
            "  cdx rotate --dry-run\n"
            "  cdx rotate --json\n"
        ),
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

    # -- all --
    all_parser = sub.add_parser(
        "all",
        help="show all keys cards dashboard (v1 style)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cdx all\n"
            "  cdx all --only weekly\n"
            "  cdx all --json\n"
        ),
    )
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

    # -- run-server (hidden) --
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
