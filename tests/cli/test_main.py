"""Tests for CLI main module - core functionality."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from cdx_proxy_cli_v2.cli.main import (
    handle_doctor,
    handle_migrate,
    handle_reset,
    handle_status,
    handle_stop,
    _settings_from_args,
    format_shell_exports,
    main,
)


@pytest.fixture
def temp_auth_dir(tmp_path: Path) -> str:
    """Create temp auth dir with cleanup."""
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    return str(auth_dir)


class TestHandleMigrate:
    """Tests for handle_migrate function."""

    def test_handle_migrate_dry_run(self, capsys, tmp_path: Path):
        """Test migrate --dry-run shows what would be migrated."""
        # Create V1 files
        v1_dir = tmp_path / "v1"
        v1_dir.mkdir()
        (v1_dir / "rr_proxy.pid").write_text("12345")
        (v1_dir / "rr_proxy.state.json").write_text('{"status": "running"}')
        
        args = argparse.Namespace(
            v1_auth_dir=str(v1_dir),
            dry_run=True,
        )
        
        result = handle_migrate(args)
        
        captured = capsys.readouterr()
        assert result == 0
        assert "Would migrate: rr_proxy.pid" in captured.out
        assert "This was a dry run" in captured.out

    def test_handle_migrate_actual(self, capsys, tmp_path: Path):
        """Test migrate actually moves files."""
        # Create V1 files
        v1_dir = tmp_path / "v1"
        v1_dir.mkdir()
        (v1_dir / "rr_proxy.pid").write_text("12345")
        (v1_dir / "rr_proxy.state.json").write_text('{"status": "running"}')
        
        args = argparse.Namespace(
            v1_auth_dir=str(v1_dir),
            dry_run=False,
        )
        
        result = handle_migrate(args)
        
        captured = capsys.readouterr()
        assert result == 0
        assert "Migrated: rr_proxy.pid" in captured.out
        assert (v1_dir / "rr_proxy_v2.pid").exists()

    def test_handle_migrate_v1_dir_not_found(self, capsys):
        """Test migrate with non-existent V1 directory."""
        args = argparse.Namespace(
            v1_auth_dir="/nonexistent/path",
            dry_run=False,
        )
        
        result = handle_migrate(args)
        
        captured = capsys.readouterr()
        assert result == 1
        assert "Error: V1 auth directory not found" in captured.err


class TestHandleStatus:
    """Tests for handle_status function."""

    def test_handle_status_json_output(self, capsys, temp_auth_dir, monkeypatch):
        """Test status --json returns machine-readable output."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        monkeypatch.setenv("CLIPROXY_HOST", "127.0.0.1")
        monkeypatch.setenv("CLIPROXY_PORT", "8080")
        monkeypatch.setenv("CLIPROXY_UPSTREAM", "https://chatgpt.com")
        monkeypatch.setenv("CLIPROXY_MANAGEMENT_KEY", "test-key")
        
        args = argparse.Namespace(
            auth_dir=None,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            json=True,
        )
        
        with patch('cdx_proxy_cli_v2.cli.main.service_status') as mock_status:
            mock_status.return_value = {
                "pid": 12345,
                "pid_running": True,
                "healthy": True,
                "base_url": "http://127.0.0.1:8080",
            }
            result = handle_status(args)
        
        captured = capsys.readouterr()
        assert result == 0
        output = json.loads(captured.out)
        assert "pid" in output

    def test_handle_status_not_running(self, capsys, temp_auth_dir, monkeypatch):
        """Test status when proxy is not running."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        
        args = argparse.Namespace(
            auth_dir=None,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            json=False,
        )
        
        with patch('cdx_proxy_cli_v2.cli.main.service_status') as mock_status:
            mock_status.return_value = {"pid": None, "pid_running": False}
            result = handle_status(args)
        
        assert result == 0


class TestHandleStop:
    """Tests for handle_stop function."""

    def test_handle_stop_not_running(self, capsys, temp_auth_dir, monkeypatch):
        """Test stop when proxy is not running."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
        
        args = argparse.Namespace(
            auth_dir=None,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
        )
        
        with patch('cdx_proxy_cli_v2.cli.main.service_status') as mock_status:
            mock_status.return_value = {"pid": None, "pid_running": False}
            result = handle_stop(args)
        
        assert result == 0


class TestDoctorResetPreflight:
    """Tests for shared doctor/reset healthy proxy preflight."""

    def test_handle_doctor_returns_error_when_proxy_not_healthy(self, capsys, temp_auth_dir):
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            json=False,
        )

        with patch('cdx_proxy_cli_v2.cli.main.service_status') as mock_status, patch('cdx_proxy_cli_v2.cli.main.fetch_json') as mock_fetch:
            mock_status.return_value = {
                "healthy": False,
                "base_url": "http://127.0.0.1:8080",
            }
            result = handle_doctor(args)

        captured = capsys.readouterr()
        assert result == 1
        assert "Proxy is not healthy/running" in captured.err
        mock_fetch.assert_not_called()

    def test_handle_reset_returns_error_when_proxy_not_healthy(self, capsys, temp_auth_dir):
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            name=None,
            state=None,
            json=False,
        )

        with patch('cdx_proxy_cli_v2.cli.main.service_status') as mock_status, patch('cdx_proxy_cli_v2.cli.main.fetch_json') as mock_fetch:
            mock_status.return_value = {
                "healthy": False,
                "base_url": "http://127.0.0.1:8080",
            }
            result = handle_reset(args)

        captured = capsys.readouterr()
        assert result == 1
        assert "Proxy is not healthy/running" in captured.err
        mock_fetch.assert_not_called()

    def test_handle_reset_urlencodes_query_params(self, temp_auth_dir):
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            name="foo&state=blacklist.json",
            state="probation",
            json=False,
        )

        with patch('cdx_proxy_cli_v2.cli.main.service_status') as mock_status, patch('cdx_proxy_cli_v2.cli.main.fetch_json') as mock_fetch:
            mock_status.return_value = {
                "healthy": True,
                "base_url": "http://127.0.0.1:8080",
            }
            mock_fetch.return_value = {"reset": 1}
            result = handle_reset(args)

        assert result == 0
        assert mock_fetch.call_args.kwargs["path"] == "/reset?name=foo%26state%3Dblacklist.json&state=probation"


class TestSettingsFromArgs:
    """Tests for _settings_from_args function."""

    def test_settings_from_args_cli_override(self, temp_auth_dir, monkeypatch):
        """Test CLI args override env vars."""
        monkeypatch.setenv("CLIPROXY_AUTH_DIR", "/env/auths")
        monkeypatch.setenv("CLIPROXY_HOST", "127.0.0.1")
        monkeypatch.setenv("CLIPROXY_PORT", "8080")
        monkeypatch.setenv("CLIPROXY_UPSTREAM", "https://chatgpt.com")
        monkeypatch.setenv("CLIPROXY_MANAGEMENT_KEY", "env-key")
        
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,  # Override env
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
        )
        
        settings = _settings_from_args(args)

        assert settings.auth_dir == temp_auth_dir  # CLI override


class TestCliContracts:
    """Tests for user-facing CLI contracts."""

    def test_main_returns_user_error_for_invalid_cli_port(self, capsys):
        result = main(["status", "--port", "70000"])

        captured = capsys.readouterr()
        assert result == 2
        assert "port must be between 0 and 65535" in captured.err

    def test_pyproject_registers_cdx_and_cdx2_scripts(self):
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        scripts = data["project"]["scripts"]
        assert scripts["cdx"] == "cdx_proxy_cli_v2.cli.main:main"
        assert scripts["cdx2"] == "cdx_proxy_cli_v2.cli.main:main"


class TestFormatShellExports:
    """Tests for format_shell_exports function."""

    def test_formats_simple_values(self):
        """Test export formatting."""
        exports = {
            "CLIPROXY_AUTH_DIR": "/test/auths",
            "CLIPROXY_HOST": "127.0.0.1",
            "CLIPROXY_PORT": "8080",
        }
        
        output = format_shell_exports(exports)
        
        assert "export CLIPROXY_AUTH_DIR='/test/auths'" in output
        assert "export CLIPROXY_HOST='127.0.0.1'" in output
        assert "export CLIPROXY_PORT='8080'" in output

    def test_escapes_single_quotes(self):
        """Test single quote escaping."""
        exports = {
            "CLIPROXY_AUTH_DIR": "/test/auth's",
        }
        
        output = format_shell_exports(exports)
        
        # The function escapes single quotes by ending quote, adding escaped quote, starting new quote
        assert "'/test/auth" in output
