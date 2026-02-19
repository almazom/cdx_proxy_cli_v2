# Card P0-001: Remove plaintext token storage - use OS keyring

## Quick Info

| Field | Value |
|-------|-------|
| **Priority** | P0 (Critical) |
| **Story Points** | 5 |
| **Expert Source** | Security Auditor |
| **Status** | Pending |
| **Dependencies** | None |
| **Blocks** | P0-002 |

---

## Full Context

### Problem

API tokens are currently stored as **plaintext JSON files** in `~/.codex/_auths/`. Any process or user with read access to this directory can extract all API tokens.

**CVSS Score:** ~7.5 (High)

### Current Code

**File:** `src/cdx_proxy_cli_v2/auth/store.py:70-88`

```python
def load_auth_records(auth_dir: str) -> List[AuthRecord]:
    records: List[AuthRecord] = []
    for path in iter_auth_json_files(auth_dir):
        raw, error = read_auth_json(path)
        if error or raw is None:
            continue
        token, email, account_id = extract_auth_fields(raw)
        if not token:
            continue
        records.append(
            AuthRecord(
                name=path.name,
                path=str(path),
                token=token,  # <-- Plaintext token stored in memory AND on disk
                email=email,
                account_id=account_id,
            )
        )
    return records
```

### Why This Matters

1. **Complete credential compromise** if auth directory is accessed
2. **No encryption at rest** - tokens persist indefinitely
3. **Violates security best practices** for credential storage
4. **Blocks P0-002** which secures the management key

---

## Implementation Steps

### Step 1: Add keyring dependency

```bash
# Add to pyproject.toml dependencies
pip install keyring
```

**File:** `pyproject.toml`

```toml
dependencies = [
  "rich>=13.7,<15",
  "keyring>=24.0",
]
```

### Step 2: Update auth/store.py to use keyring

**File:** `src/cdx_proxy_cli_v2/auth/store.py`

```python
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import keyring  # NEW IMPORT

SERVICE_NAME = "cdx_proxy_cli_v2"

# ... existing code ...

def load_auth_records(auth_dir: str) -> List[AuthRecord]:
    """Load auth records, retrieving tokens from OS keyring."""
    records: List[AuthRecord] = []
    for path in iter_auth_json_files(auth_dir):
        raw, error = read_auth_json(path)
        if error or raw is None:
            continue
        # Extract non-token fields from file
        email = raw.get("email")
        account_id = None
        if "tokens" in raw and isinstance(raw["tokens"], dict):
            account_id = raw["tokens"].get("account_id")
        
        # Retrieve token from keyring using file stem as identifier
        token = keyring.get_password(SERVICE_NAME, path.stem)
        if not token:
            # Fallback: try to extract from file for migration
            token = raw.get("access_token")
        
        if not token:
            continue
        
        records.append(
            AuthRecord(
                name=path.name,
                path=str(path),
                token=token,
                email=email,
                account_id=account_id,
            )
        )
    return records


def save_auth_record(auth_dir: str, record: AuthRecord) -> None:
    """Save auth record, storing token in OS keyring."""
    path = Path(os.path.expanduser(auth_dir)) / record.name
    
    # Store non-token data in JSON file
    data: Dict[str, Any] = {}
    if record.email:
        data["email"] = record.email
    if record.account_id:
        data["tokens"] = {"account_id": record.account_id}
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    
    # Store token in keyring
    keyring.set_password(SERVICE_NAME, path.stem, record.token)
```

### Step 3: Create migration script

**File:** `scripts/migrate_tokens_to_keyring.py`

```python
#!/usr/bin/env python3
"""Migrate plaintext tokens from auth JSON files to OS keyring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
import keyring

SERVICE_NAME = "cdx_proxy_cli_v2"

def migrate_auth_dir(auth_dir: Path) -> int:
    """Migrate all tokens in auth directory. Returns count of migrated tokens."""
    migrated = 0
    
    for json_file in auth_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            token = data.get("access_token")
            
            if token:
                # Store in keyring
                keyring.set_password(SERVICE_NAME, json_file.stem, token)
                
                # Remove from JSON file
                del data["access_token"]
                json_file.write_text(json.dumps(data, indent=2) + "\n")
                
                print(f"✓ Migrated: {json_file.name}")
                migrated += 1
            else:
                print(f"⊘ Skipped (no token): {json_file.name}")
        except Exception as e:
            print(f"✗ Failed: {json_file.name} - {e}", file=sys.stderr)
    
    return migrated

if __name__ == "__main__":
    auth_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".codex" / "_auths"
    
    if not auth_dir.exists():
        print(f"Error: {auth_dir} does not exist", file=sys.stderr)
        sys.exit(1)
    
    count = migrate_auth_dir(auth_dir)
    print(f"\nMigrated {count} token(s) to OS keyring")
```

### Step 4: Write tests

**File:** `tests/auth/test_keyring_store.py`

```python
"""Tests for keyring-based token storage."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from cdx_proxy_cli_v2.auth.store import load_auth_records, save_auth_record, AuthRecord


@pytest.fixture
def mock_keyring(monkeypatch):
    """Mock keyring for testing."""
    storage = {}
    
    def mock_get_password(service, name):
        return storage.get(f"{service}:{name}")
    
    def mock_set_password(service, name, password):
        storage[f"{service}:{name}"] = password
    
    monkeypatch.setattr("keyring.get_password", mock_get_password)
    monkeypatch.setattr("keyring.set_password", mock_set_password)
    
    return storage


def test_load_auth_records_from_keyring(mock_keyring, tmp_path):
    """Test loading tokens from keyring."""
    # Setup: create auth file without token
    auth_file = tmp_path / "test_auth.json"
    auth_file.write_text('{"email": "test@example.com"}')
    
    # Store token in keyring
    mock_keyring["cdx_proxy_cli_v2:test_auth"] = "secret-token-123"
    
    # Load records
    records = load_auth_records(str(tmp_path))
    
    assert len(records) == 1
    assert records[0].token == "secret-token-123"
    assert records[0].email == "test@example.com"


def test_save_auth_record_stores_in_keyring(mock_keyring, tmp_path):
    """Test saving stores token in keyring."""
    record = AuthRecord(
        name="new_auth.json",
        path=str(tmp_path / "new_auth.json"),
        token="new-token-456",
        email="new@example.com",
    )
    
    save_auth_record(str(tmp_path), record)
    
    # Verify token in keyring
    assert mock_keyring.get("cdx_proxy_cli_v2:new_auth") == "new-token-456"
    
    # Verify file doesn't contain token
    auth_file = tmp_path / "new_auth.json"
    data = json.loads(auth_file.read_text())
    assert "access_token" not in data
```

### Step 5: Update README

Add to **README.md** under Security Defaults:

```markdown
## Security: Token Storage

Tokens are stored in your OS keyring (not plaintext files):

- **Linux:** Secret Service API (GNOME Keyring, KWallet)
- **macOS:** Keychain
- **Windows:** Credential Vault

For headless servers, configure keyring backend:

```bash
# Use file-based keyring (encrypted)
pip install keyrings.alt
export PYTHON_KEYRING_BACKEND=keyrings.alt.file.EncryptedKeyring
```
```

---

## Testing Checklist

| Test | Command | Expected |
|------|---------|----------|
| Keyring dependency installed | `python -c 'import keyring'` | No error |
| Load records from keyring | `pytest tests/auth/test_keyring_store.py` | Pass |
| Migration script works | `python scripts/migrate_tokens_to_keyring.py` | Migrates tokens |
| Save stores in keyring | `pytest tests/auth/test_keyring_store.py::test_save_auth_record_stores_in_keyring` | Pass |

---

## Risks & Gotchas

| Risk | Mitigation |
|------|------------|
| Keyring not available on headless servers | Provide fallback to file-based encrypted keyring |
| Migration fails mid-way | Script is idempotent - can re-run safely |
| Backward compatibility | Fallback to reading from JSON if keyring empty |
| CI/CD environments | Use environment variable injection for tokens |

---

## Dependencies

- None (this is a foundational security fix)

---

## Git Commands

```bash
# Create branch
git checkout -b feature/keyring-token-storage

# Stage changes
git add pyproject.toml src/cdx_proxy_cli_v2/auth/store.py scripts/migrate_tokens_to_keyring.py tests/auth/test_keyring_store.py README.md

# Commit
git commit -m "feat: store tokens in OS keyring instead of plaintext

- Add keyring dependency for secure credential storage
- Migrate existing tokens from JSON files to keyring
- Provide migration script for backward compatibility
- Add tests for keyring-based storage

Security: Tokens now encrypted at rest using OS-native keyring"
```

---

## Pre-Completion Checklist

- [ ] All tests pass: `pytest tests/auth/test_keyring_store.py`
- [ ] Migration script tested on sample data
- [ ] README updated with keyring setup instructions
- [ ] No plaintext tokens in new auth files
- [ ] Backward compatibility maintained for existing files

---

## Report Reference

- **Expert:** Security Auditor
- **Finding:** #1 - CRITICAL: Plaintext Token Storage in Auth Files
- **Report Section:** Findings → CRITICAL → Finding 1
