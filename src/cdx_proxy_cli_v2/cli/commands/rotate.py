from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cdx_proxy_cli_v2.auth.store import read_auth_json
from cdx_proxy_cli_v2.cli.doctor_view import _extract_accounts
from cdx_proxy_cli_v2.cli.fs import _atomic_write_json, _get_codex_home
from cdx_proxy_cli_v2.cli.shared import (
    ROTATE_HEALTH_TIMEOUT_SECONDS,
    _healthy_base_url_or_none,
    _management_headers,
    _settings_from_args,
)
from cdx_proxy_cli_v2.observability.limits_history import read_latest_limits_snapshot
from cdx_proxy_cli_v2.proxy.http_client import fetch_json


def _rotation_accounts(
    *, settings, base_url: str, headers: dict[str, str]
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
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


def handle_rotate(args: argparse.Namespace) -> int:
    """Rotate active auth key for codex CLI."""
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
        print("All keys are in cooldown, blacklist, or probation state.", file=sys.stderr)
        print("Run `cdx doctor` to see current auth states.", file=sys.stderr)
        return 1

    healthy_auths.sort(
        key=lambda a: (int(a.get("used") or 0), str(a.get("file") or ""))
    )
    selected = healthy_auths[0]

    selected_file = str(selected.get("file") or "")
    selected_email = str(selected.get("email") or selected.get("account") or "")
    selected_used = int(selected.get("used") or 0)

    auth_dir_path = Path(settings.auth_dir).expanduser().resolve()
    source_path = auth_dir_path / selected_file

    codex_home = _get_codex_home()
    dest_path = codex_home / "auth.json"

    dry_run = bool(getattr(args, "dry_run", False))
    json_output = bool(getattr(args, "json", False))

    if dry_run:
        if json_output:
            print(json.dumps({
                "dry_run": True,
                "selected": {"file": selected_file, "email": selected_email, "used": selected_used},
                "source": str(source_path),
                "destination": str(dest_path),
            }, indent=2))
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

    raw, error = read_auth_json(source_path)
    if error or raw is None:
        print(f"Error: Failed to read auth file: {error}", file=sys.stderr)
        return 1

    try:
        _atomic_write_json(dest_path, raw)
    except Exception as exc:
        print(f"Error: Failed to write auth file: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps({
            "success": True,
            "selected": {"file": selected_file, "email": selected_email, "used": selected_used},
            "destination": str(dest_path),
        }, indent=2))
    else:
        print(f"Rotated to auth key: {selected_file}")
        if selected_email:
            print(f"  Email: {selected_email}")
        print(f"  Used count: {selected_used}")
        print(f"  Written to: {dest_path}")

    return 0
