"""Tests for keyring-based token storage."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from cdx_proxy_cli_v2.auth.store import load_auth_records, save_auth_record, AuthRecord, KEYRING_AVAILABLE


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


@pytest.mark.skipif(not KEYRING_AVAILABLE, reason="keyring not installed")
def test_load_auth_records_from_keyring(mock_keyring, tmp_path):
    """Test loading tokens from keyring."""
    # Auth file with token - keyring should override
    auth_file = tmp_path / "test_auth.json"
    auth_file.write_text('{"email": "test@example.com", "access_token": "old-token"}')
    
    mock_keyring["cdx_proxy_cli_v2:test_auth"] = "secret-token-123"
    
    records = load_auth_records(str(tmp_path))
    
    assert len(records) == 1
    assert records[0].token == "secret-token-123"
    assert records[0].email == "test@example.com"


@pytest.mark.skipif(not KEYRING_AVAILABLE, reason="keyring not installed")
def test_save_auth_record_stores_in_keyring(mock_keyring, tmp_path):
    """Test saving stores token in keyring."""
    record = AuthRecord(
        name="new_auth.json",
        path=str(tmp_path / "new_auth.json"),
        token="new-token-456",
        email="new@example.com",
    )
    
    save_auth_record(str(tmp_path), record)
    
    assert mock_keyring.get("cdx_proxy_cli_v2:new_auth") == "new-token-456"
    
    auth_file = tmp_path / "new_auth.json"
    data = json.loads(auth_file.read_text())
    assert "access_token" not in data
    assert data["email"] == "new@example.com"


@pytest.mark.skipif(not KEYRING_AVAILABLE, reason="keyring not installed")
def test_load_auth_records_fallback_to_file(mock_keyring, tmp_path):
    """Test fallback to file when keyring has no token."""
    auth_file = tmp_path / "fallback_auth.json"
    auth_file.write_text('{"access_token": "file-token-789", "email": "fallback@example.com"}')
    
    records = load_auth_records(str(tmp_path))
    
    assert len(records) == 1
    assert records[0].token == "file-token-789"


def test_load_auth_records_without_keyring(tmp_path):
    """Test loading works without keyring (backward compatibility)."""
    auth_file = tmp_path / "no_keyring_auth.json"
    auth_file.write_text('{"access_token": "plain-token", "email": "test@example.com"}')
    
    with patch('cdx_proxy_cli_v2.auth.store.KEYRING_AVAILABLE', False):
        records = load_auth_records(str(tmp_path))
    
    assert len(records) == 1
    assert records[0].token == "plain-token"


@pytest.mark.skipif(not KEYRING_AVAILABLE, reason="keyring not installed")
def test_iter_auth_json_files_prevents_traversal(tmp_path):
    """Test that auth file iteration prevents path traversal."""
    # Create a symlink to a file outside auth dir
    outside_file = tmp_path / "outside.json"
    outside_file.write_text('{"access_token": "outside"}')
    
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    
    # Create symlink inside auth dir pointing outside
    symlink = auth_dir / "link.json"
    symlink.symlink_to(outside_file)
    
    # Create a legitimate file inside auth dir
    legit_file = auth_dir / "legit.json"
    legit_file.write_text('{"access_token": "legit"}')
    
    files = [f.name for f in load_auth_records.__globals__['iter_auth_json_files'](str(auth_dir))]
    
    # Should only include legitimate file, not symlink to outside
    assert "legit.json" in files
    assert "link.json" not in files
