from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cdx_proxy_cli_v2.auth.rotation import RoundRobinAuthPool
from cdx_proxy_cli_v2.auth.store import load_auth_records
from cdx_proxy_cli_v2.auth.store import read_auth_json
from cdx_proxy_cli_v2.cli.fs import _atomic_write_json, _get_codex_home
from cdx_proxy_cli_v2.cli.shared import (
    ROTATE_HEALTH_TIMEOUT_SECONDS,
    _fetch_runtime_next_auth,
    _management_headers,
    _settings_from_args,
)
from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.runtime.service import service_status


def _detect_proxy_active(*, base_url: str | None, headers: dict[str, str]) -> bool:
    if not base_url:
        return False
    try:
        payload = fetch_json(
            base_url=base_url,
            path="/health",
            headers=headers,
            timeout=ROTATE_HEALTH_TIMEOUT_SECONDS,
        )
    except Exception:
        return False
    return isinstance(payload, dict)


def _select_local_next_auth(auth_dir: str) -> dict[str, Any] | None:
    records = load_auth_records(auth_dir, prefer_keyring=False)
    if not records:
        return None
    pool = RoundRobinAuthPool()
    pool.load(records)
    return pool.preview_next_pick()


def _selected_summary(*, selected_file: str, selected_email: str, selected_used: int) -> dict[str, Any]:
    return {
        "file": selected_file,
        "email": selected_email,
        "used": selected_used,
    }


def _selected_label(selected_file: str, selected_email: str) -> str:
    if selected_email:
        return f"{selected_file} ({selected_email})"
    return selected_file


def handle_rotate(args: argparse.Namespace) -> int:
    """Rotate active auth key for codex CLI."""
    settings = _settings_from_args(args)
    status_payload = service_status(settings)
    base_url_raw = status_payload.get("base_url") or settings.base_url
    base_url = str(base_url_raw).strip() or None
    headers = _management_headers(settings)
    proxy_active = _detect_proxy_active(base_url=base_url, headers=headers)
    try:
        if proxy_active and base_url is not None:
            selected = _fetch_runtime_next_auth(
                base_url=base_url,
                headers=headers,
                timeout=ROTATE_HEALTH_TIMEOUT_SECONDS,
            )
        else:
            selected = _select_local_next_auth(settings.auth_dir)
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
    fallback = bool(getattr(args, "fallback", False))
    no_write = bool(getattr(args, "no_write", False))
    json_output = bool(getattr(args, "json", False))
    selected_payload = _selected_summary(
        selected_file=selected_file,
        selected_email=selected_email,
        selected_used=selected_used,
    )

    if dry_run:
        if json_output:
            print(json.dumps({
                "success": True,
                "dry_run": True,
                "proxy_active": proxy_active,
                "selected": selected_payload,
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

    should_write = not no_write and (not proxy_active or fallback)
    if not should_write:
        if json_output:
            print(json.dumps({
                "success": True,
                "proxy_active": proxy_active,
                "written": False,
                "selected": selected_payload,
                "destination": str(dest_path),
            }, indent=2))
        else:
            if proxy_active:
                print("Proxy is active — key selection is managed by the pool.")
            print(f"Next recommended key: {_selected_label(selected_file, selected_email)}")
            if no_write:
                print("No-write mode: auth.json was not modified.")
            if proxy_active:
                print("Use --fallback to force write to ~/.codex/auth.json")
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
            "proxy_active": proxy_active,
            "written": True,
            "selected": selected_payload,
            "destination": str(dest_path),
        }, indent=2))
    else:
        print(f"Rotated to auth key: {selected_file}")
        if selected_email:
            print(f"  Email: {selected_email}")
        print(f"  Used count: {selected_used}")
        print(f"  Written to: {dest_path}")

    return 0
