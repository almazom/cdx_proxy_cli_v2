from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cdx_proxy_cli_v2.auth.store import read_auth_json
from cdx_proxy_cli_v2.cli.fs import _atomic_write_json, _get_codex_home
from cdx_proxy_cli_v2.cli.shared import (
    ROTATE_HEALTH_TIMEOUT_SECONDS,
    _fetch_runtime_next_auth,
    _healthy_base_url_or_none,
    _management_headers,
    _settings_from_args,
)


def handle_rotate(args: argparse.Namespace) -> int:
    """Rotate active auth key for codex CLI."""
    settings = _settings_from_args(args)
    base_url = _healthy_base_url_or_none(settings)
    if base_url is None:
        return 1

    headers = _management_headers(settings)
    try:
        selected = _fetch_runtime_next_auth(
            base_url=base_url,
            headers=headers,
            timeout=ROTATE_HEALTH_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        print(f"Failed to fetch next auth selection: {exc}", file=sys.stderr)
        return 1

    if not isinstance(selected, dict):
        print("Error: No healthy auth keys available.", file=sys.stderr)
        print("All keys are in cooldown, blacklist, or probation state.", file=sys.stderr)
        print("Run `cdx doctor` to see current auth states.", file=sys.stderr)
        return 1

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
