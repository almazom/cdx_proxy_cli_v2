from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


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

    v1_files = [
        "rr_proxy.pid",
        "rr_proxy.state.json",
        "rr_proxy.log",
        "rr_proxy.events.jsonl",
    ]
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
                content = v1_file.read_text(encoding="utf-8")
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
