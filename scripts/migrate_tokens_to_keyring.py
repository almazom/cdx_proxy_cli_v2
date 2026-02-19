#!/usr/bin/env python3
"""Migrate plaintext tokens from auth JSON files to OS keyring."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import keyring
    SERVICE_NAME = "cdx_proxy_cli_v2"
except ImportError:
    print("Error: keyring not installed. Run: pip install keyring", file=sys.stderr)
    sys.exit(1)


def migrate_auth_dir(auth_dir: Path) -> int:
    """Migrate all tokens in auth directory. Returns count of migrated tokens."""
    migrated = 0
    skipped = 0
    failed = 0
    
    for json_file in auth_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            token = data.get("access_token")
            
            if token:
                # Store in keyring
                keyring.set_password(SERVICE_NAME, json_file.stem, token)
                
                # Remove from JSON file
                del data["access_token"]
                json_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                
                print(f"✓ Migrated: {json_file.name}")
                migrated += 1
            else:
                print(f"⊘ Skipped (no token): {json_file.name}")
                skipped += 1
        except Exception as e:
            print(f"✗ Failed: {json_file.name} - {e}", file=sys.stderr)
            failed += 1
    
    return migrated, skipped, failed


def main():
    if len(sys.argv) > 1:
        auth_dir = Path(sys.argv[1])
    else:
        auth_dir = Path.home() / ".codex" / "_auths"
    
    if not auth_dir.exists():
        print(f"Error: {auth_dir} does not exist", file=sys.stderr)
        print("Usage: python migrate_tokens_to_keyring.py [auth_dir]", file=sys.stderr)
        sys.exit(1)
    
    print(f"Migrating tokens from: {auth_dir}")
    print("-" * 50)
    
    migrated, skipped, failed = migrate_auth_dir(auth_dir)
    
    print("-" * 50)
    print(f"Migrated: {migrated}")
    print(f"Skipped:  {skipped}")
    print(f"Failed:   {failed}")
    
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
