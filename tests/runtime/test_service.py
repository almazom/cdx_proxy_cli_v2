"""Tests for runtime service lifecycle."""

from __future__ import annotations

import json
import os
import socket
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from cdx_proxy_cli_v2.runtime.service import (
    start_service,
    stop_service,
    service_status,
    tail_service_logs,
    _load_state,
    _save_state,
    STATE_SCHEMA_VERSION,
    pick_free_port,
    probe_debug,
)


@pytest.fixture
def temp_auth_dir(tmp_path: Path) -> str:
    """Create temp auth dir with cleanup."""
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    return str(auth_dir)


class TestStateSchemaVersioning:
    """Tests for state schema versioning."""

    def test_save_state_includes_schema_version(self, tmp_path: Path):
        """Test _save_state includes $schema_version."""
        state_file = tmp_path / "test.state.json"
        payload = {"status": "running", "pid": 12345}
        
        _save_state(state_file, payload)
        
        data = json.loads(state_file.read_text())
        assert data["$schema_version"] == STATE_SCHEMA_VERSION
        assert "$written_at" in data
        assert data["status"] == "running"
        assert data["pid"] == 12345

    def test_load_state_validates_schema_version(self, tmp_path: Path):
        """Test _load_state validates schema version."""
        state_file = tmp_path / "test.state.json"
        
        # Valid version
        valid_data = {
            "$schema_version": STATE_SCHEMA_VERSION,
            "status": "running",
        }
        state_file.write_text(json.dumps(valid_data))
        
        result = _load_state(state_file)
        assert result["status"] == "running"

    def test_load_state_rejects_old_version(self, tmp_path: Path):
        """Test _load_state rejects mismatched schema version."""
        state_file = tmp_path / "test.state.json"
        
        # Old version
        old_data = {
            "$schema_version": "0.9.0",
            "status": "running",
        }
        state_file.write_text(json.dumps(old_data))
        
        result = _load_state(state_file)
        assert result == {}  # Returns empty for incompatible version

    def test_load_state_handles_missing_version(self, tmp_path: Path):
        """Test _load_state handles missing schema version (backward compat)."""
        state_file = tmp_path / "test.state.json"
        
        # No version field (old format) - defaults to 1.0.0 which matches
        old_data = {"status": "running"}
        state_file.write_text(json.dumps(old_data))
        
        result = _load_state(state_file)
        # Missing version defaults to 1.0.0, which matches current version
        assert result["status"] == "running"

    def test_load_state_handles_invalid_json(self, tmp_path: Path):
        """Test _load_state handles invalid JSON."""
        state_file = tmp_path / "test.state.json"
        state_file.write_text("not-valid-json")
        
        result = _load_state(state_file)
        assert result == {}

    def test_load_state_handles_missing_file(self, tmp_path: Path):
        """Test _load_state handles missing file."""
        state_file = tmp_path / "nonexistent.state.json"
        
        result = _load_state(state_file)
        assert result == {}


class TestStartService:
    """Tests for start_service function."""

    def test_start_service_creates_pid_file(self, temp_auth_dir, monkeypatch):
        """Test start_service creates PID file."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        monkeypatch.setenv("CLIPROXY_HOST", "127.0.0.1")
        monkeypatch.setenv("CLIPROXY_PORT", "0")  # Auto-assign
        monkeypatch.setenv("CLIPROXY_UPSTREAM", "https://chatgpt.com")
        monkeypatch.setenv("CLIPROXY_MANAGEMENT_KEY", "test-key")
        
        with patch('cdx_proxy_cli_v2.runtime.service._spawn') as mock_spawn:
            mock_process = MagicMock()
            mock_process.pid = 99999
            mock_spawn.return_value = mock_process
            
            with patch('cdx_proxy_cli_v2.runtime.service._wait_for_ready') as mock_wait:
                mock_wait.return_value = {"status": "running"}
                
                from cdx_proxy_cli_v2.config.settings import build_settings
                settings = build_settings()
                result = start_service(settings)
        
        assert result.started is True
        pid_file = Path(temp_auth_dir) / "rr_proxy_v2.pid"
        assert pid_file.exists()

    def test_start_service_already_running(self, temp_auth_dir, monkeypatch):
        """Test start_service when already running."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        
        # Create PID file with a fake PID (use current PID so _is_pid_running returns True)
        pid_file = Path(temp_auth_dir) / "rr_proxy_v2.pid"
        pid_file.write_text(str(os.getpid()))
        
        # Create state file with valid schema version
        state_file = Path(temp_auth_dir) / "rr_proxy_v2.state.json"
        state_data = {
            "$schema_version": STATE_SCHEMA_VERSION,
            "status": "running",
            "base_url": "http://127.0.0.1:9999",
        }
        state_file.write_text(json.dumps(state_data))
        
        with patch('cdx_proxy_cli_v2.runtime.service.probe_debug') as mock_probe:
            mock_probe.return_value = {"status": "running", "port": 9999, "host": "127.0.0.1"}
            
            from cdx_proxy_cli_v2.config.settings import build_settings
            settings = build_settings()
            result = start_service(settings)
        
        assert result.started is False


class TestStopService:
    """Tests for stop_service function."""

    def test_stop_service_sends_shutdown(self, temp_auth_dir, monkeypatch):
        """Test stop_service sends shutdown request."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        
        # Create PID file with current PID so _is_pid_running returns True
        pid_file = Path(temp_auth_dir) / "rr_proxy_v2.pid"
        pid_file.write_text(str(os.getpid()))
        
        from cdx_proxy_cli_v2.config.settings import build_settings
        settings = build_settings()
        
        with patch('cdx_proxy_cli_v2.runtime.service.fetch_json') as mock_fetch:
            mock_fetch.return_value = {"status": "shutting_down"}
            with patch('cdx_proxy_cli_v2.runtime.service._terminate_pid') as mock_terminate:
                with patch('cdx_proxy_cli_v2.runtime.service._remove_file'):
                    result = stop_service(settings)
        
        assert result is True
        mock_fetch.assert_called_once()

    def test_stop_service_not_running(self, temp_auth_dir, monkeypatch):
        """Test stop_service when not running."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        
        from cdx_proxy_cli_v2.config.settings import build_settings
        settings = build_settings()
        result = stop_service(settings)
        assert result is False


class TestServiceStatus:
    """Tests for service_status function."""

    def test_service_status_running(self, temp_auth_dir, monkeypatch):
        """Test service_status detects running proxy."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        
        # Create PID file with current PID so _is_pid_running returns True
        pid_file = Path(temp_auth_dir) / "rr_proxy_v2.pid"
        pid_file.write_text(str(os.getpid()))
        
        # Create state file
        state_file = Path(temp_auth_dir) / "rr_proxy_v2.state.json"
        state_data = {
            "$schema_version": STATE_SCHEMA_VERSION,
            "status": "running",
            "pid": os.getpid(),
        }
        state_file.write_text(json.dumps(state_data))
        
        from cdx_proxy_cli_v2.config.settings import build_settings
        settings = build_settings()
        result = service_status(settings)
        
        assert result["pid_running"] is True

    def test_service_status_not_running(self, temp_auth_dir, monkeypatch):
        """Test service_status when not running."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        
        from cdx_proxy_cli_v2.config.settings import build_settings
        settings = build_settings()
        result = service_status(settings)
        
        assert result["pid"] is None
        assert result["pid_running"] is False


class TestTailServiceLogs:
    """Tests for tail_service_logs function."""

    def test_tail_service_logs_empty(self, temp_auth_dir):
        """Test tail_service_logs when no logs exist."""
        result = tail_service_logs(temp_auth_dir, lines=50)
        assert result == []

    def test_tail_service_logs_with_content(self, temp_auth_dir):
        """Test tail_service_logs with log content."""
        log_file = Path(temp_auth_dir) / "rr_proxy_v2.log"
        log_file.write_text("\n".join([f"Log line {i}" for i in range(100)]))
        
        result = tail_service_logs(temp_auth_dir, lines=10)
        
        assert len(result) == 10
        assert "Log line 99" in result[-1]


class TestPickFreePort:
    """Tests for pick_free_port function."""

    def test_pick_free_port_returns_available(self):
        """Test pick_free_port returns available port."""
        port = pick_free_port("127.0.0.1")
        
        assert isinstance(port, int)
        assert 1 <= port <= 65535
        
        # Verify port is actually available
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))


class TestProbeDebug:
    """Tests for probe_debug function."""

    def test_probe_debug_success(self):
        """Test probe_debug with successful response."""
        with patch('cdx_proxy_cli_v2.runtime.service.fetch_json') as mock_fetch:
            mock_fetch.return_value = {
                "status": "running",
                "port": 8080,
            }
            
            result = probe_debug("http://127.0.0.1:8080", "test-key")
            
            assert result is not None
            assert result["status"] == "running"

    def test_probe_debug_failure(self):
        """Test probe_debug with connection failure."""
        result = probe_debug("http://localhost:1", "test-key")
        assert result is None
