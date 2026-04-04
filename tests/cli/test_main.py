"""Tests for CLI main module - core functionality."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
import pytest
from pathlib import Path
from unittest.mock import patch

from cdx_proxy_cli_v2.cli.main import (
    _load_codex_auth_identity,
    _proxy_exports,
    _proxy_shell_setup,
    _state_bucket,
    build_parser,
    handle_all,
    handle_doctor,
    handle_limits,
    handle_migrate,
    handle_reset,
    handle_status,
    handle_stop,
    handle_rotate,
    _settings_from_args,
    format_shell_exports,
    main,
)
from cdx_proxy_cli_v2.observability.limits_history import (
    append_limits_history,
    write_latest_limits_snapshot,
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

        with patch("cdx_proxy_cli_v2.cli.commands.status.service_status") as mock_status:
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


class TestProxyShellSetup:
    """Tests for shell bootstrap emitted by `cdx proxy --print-env-only`."""

    def test_proxy_shell_setup_wraps_codex_with_config_override(self, temp_auth_dir):
        exports = _proxy_exports(
            argparse.Namespace(
                auth_dir=temp_auth_dir,
                env_path=Path(temp_auth_dir) / ".env",
            ),
            base_url="http://127.0.0.1:43123",
            host="127.0.0.1",
            port=43123,
        )

        shell_setup = _proxy_shell_setup(exports)

        assert "export CLIPROXY_BASE_URL='http://127.0.0.1:43123'" in shell_setup
        assert "codex() {" in shell_setup
        assert '-c "openai_base_url=\\"http://127.0.0.1:43123\\""' in shell_setup


class TestLoadCodexAuthIdentity:
    def test_load_codex_auth_identity_reads_auth_from_codex_home(
        self, tmp_path: Path, monkeypatch
    ):
        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()
        (codex_home / "auth.json").write_text(
            json.dumps(
                {
                    "access_token": "tok-123",
                    "email": "test@example.com",
                    "tokens": {"account_id": "acc-123"},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("CODEX_HOME", str(codex_home))

        token, email, account_id = _load_codex_auth_identity()

        assert token == "tok-123"
        assert email == "test@example.com"
        assert account_id == "acc-123"

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

        with patch("cdx_proxy_cli_v2.cli.commands.status.service_status") as mock_status:
            mock_status.return_value = {"pid": None, "pid_running": False}
            result = handle_status(args)

        assert result == 0


class TestModuleEntrypoint:
    def test_python_m_cli_main_help_is_clean(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "src")

        result = subprocess.run(
            [sys.executable, "-m", "cdx_proxy_cli_v2.cli.main", "--help"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert "RuntimeWarning" not in result.stderr


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

        with patch("cdx_proxy_cli_v2.cli.commands.stop.stop_service") as mock_stop:
            mock_stop.return_value = False
            result = handle_stop(args)

        assert result == 0


class TestHandleLimits:
    """Tests for persisted limits CLI output."""

    def test_handle_limits_json_reads_snapshot_and_history(
        self, capsys, temp_auth_dir
    ):
        write_latest_limits_snapshot(
            temp_auth_dir,
            {
                "fetched_at": 1000.0,
                "stale": False,
                "accounts": [
                    {
                        "file": "a.json",
                        "email": "a@example.com",
                        "status": "WARN",
                        "reason": "limit_5h_guardrail",
                        "reason_origin": "limit_guardrail",
                        "five_hour": {
                            "used_percent": 89.5,
                            "reset_after_seconds": 1800,
                        },
                    }
                ],
            },
        )
        append_limits_history(
            temp_auth_dir,
            {
                "fetched_at": 1000.0,
                "accounts": [
                    {
                        "file": "a.json",
                        "email": "a@example.com",
                        "status": "WARN",
                        "reason": "limit_5h_guardrail",
                        "reason_origin": "limit_guardrail",
                        "five_hour": {
                            "used_percent": 89.5,
                            "reset_after_seconds": 1800,
                        },
                    }
                ],
            },
        )

        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            limit_min_remaining_percent=None,
            max_in_flight_requests=None,
            max_pending_requests=None,
            auto_reset_on_single_key=None,
            auto_reset_streak=None,
            auto_reset_cooldown=None,
            json=True,
            tail=5,
        )

        with (
            patch("cdx_proxy_cli_v2.cli.commands.limits.service_status") as mock_status,
            patch(
                "cdx_proxy_cli_v2.cli.commands.limits._fetch_runtime_next_auth"
            ) as mock_next_auth,
        ):
            mock_status.return_value = {
                "healthy": True,
                "base_url": "http://127.0.0.1:8080",
            }
            mock_next_auth.return_value = {
                "file": "live.json",
                "email": "live@example.com",
            }
            result = handle_limits(args)

        captured = capsys.readouterr()
        assert result == 0
        payload = json.loads(captured.out)
        assert payload["snapshot"]["accounts"][0]["email"] == "a@example.com"
        assert payload["snapshot"]["next_auth_file"] == "live.json"
        assert payload["snapshot"]["next_auth_source"] == "runtime"
        assert payload["live_next_auth"]["file"] == "live.json"
        assert len(payload["history"]) == 1

    def test_handle_limits_returns_error_when_no_persisted_data(
        self, capsys, temp_auth_dir
    ):
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            limit_min_remaining_percent=None,
            max_in_flight_requests=None,
            max_pending_requests=None,
            auto_reset_on_single_key=None,
            auto_reset_streak=None,
            auto_reset_cooldown=None,
            json=False,
            tail=0,
        )

        with patch("cdx_proxy_cli_v2.cli.commands.limits.service_status") as mock_status:
            mock_status.return_value = {"healthy": False}
            result = handle_limits(args)

        captured = capsys.readouterr()
        assert result == 1
        assert "No persisted limits snapshot found" in captured.err

    def test_handle_limits_human_output_prints_history_when_requested(
        self, capsys, temp_auth_dir
    ):
        write_latest_limits_snapshot(
            temp_auth_dir,
            {
                "fetched_at": 1000.0,
                "stale": True,
                "accounts": [
                    {
                        "file": "a.json",
                        "email": "a@example.com",
                        "status": "OK",
                    }
                ],
            },
        )
        append_limits_history(
            temp_auth_dir,
            {
                "fetched_at": 1000.0,
                "accounts": [
                    {
                        "file": "a.json",
                        "email": "a@example.com",
                        "status": "OK",
                    }
                ],
            },
        )

        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            limit_min_remaining_percent=None,
            max_in_flight_requests=None,
            max_pending_requests=None,
            auto_reset_on_single_key=None,
            auto_reset_streak=None,
            auto_reset_cooldown=None,
            json=False,
            tail=1,
        )

        with patch("cdx_proxy_cli_v2.cli.commands.limits.service_status") as mock_status:
            mock_status.return_value = {"healthy": False}
            result = handle_limits(args)

        captured = capsys.readouterr()
        assert result == 0
        assert "cdx limits" in captured.out
        assert "cdx limits history" in captured.out

    def test_handle_limits_json_clears_snapshot_next_auth_when_proxy_unhealthy(
        self, capsys, temp_auth_dir
    ):
        write_latest_limits_snapshot(
            temp_auth_dir,
            {
                "fetched_at": 1000.0,
                "stale": False,
                "next_auth_file": "stale.json",
                "next_auth_email": "stale@example.com",
                "accounts": [],
            },
        )
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            limit_min_remaining_percent=None,
            max_in_flight_requests=None,
            max_pending_requests=None,
            auto_reset_on_single_key=None,
            auto_reset_streak=None,
            auto_reset_cooldown=None,
            json=True,
            tail=0,
        )

        with patch("cdx_proxy_cli_v2.cli.commands.limits.service_status") as mock_status:
            mock_status.return_value = {"healthy": False}
            result = handle_limits(args)

        captured = capsys.readouterr()
        assert result == 0
        payload = json.loads(captured.out)
        assert payload["snapshot"]["next_auth_file"] is None
        assert payload["snapshot"]["next_auth_email"] is None
        assert payload["snapshot"]["next_auth_source"] == "proxy_unavailable"


class TestDoctorResetPreflight:
    """Tests for shared doctor/reset healthy proxy preflight."""

    def test_handle_doctor_returns_error_when_proxy_not_healthy(
        self, capsys, temp_auth_dir
    ):
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

        with (
            patch("cdx_proxy_cli_v2.cli.shared.service_status") as mock_status,
            patch("cdx_proxy_cli_v2.cli.commands.doctor.fetch_json") as mock_fetch,
        ):
            mock_status.return_value = {
                "healthy": False,
                "base_url": "http://127.0.0.1:8080",
            }
            result = handle_doctor(args)

        captured = capsys.readouterr()
        assert result == 1
        assert "Proxy is not healthy/running" in captured.err
        mock_fetch.assert_not_called()

    def test_handle_reset_returns_error_when_proxy_not_healthy(
        self, capsys, temp_auth_dir
    ):
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

        with (
            patch("cdx_proxy_cli_v2.cli.shared.service_status") as mock_status,
            patch("cdx_proxy_cli_v2.cli.commands.reset.fetch_json") as mock_fetch,
        ):
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

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.reset._healthy_base_url_or_none"
            ) as mock_base_url,
            patch("cdx_proxy_cli_v2.cli.commands.reset.fetch_json") as mock_fetch,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_fetch.return_value = {"reset": 1}
            result = handle_reset(args)

        assert result == 0
        assert (
            mock_fetch.call_args.kwargs["path"]
            == "/reset?name=foo%26state%3Dblacklist.json&state=probation"
        )

    def test_handle_doctor_probe_describes_non_mutating_outcomes(
        self, capsys, temp_auth_dir
    ):
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            probe=True,
            probe_timeout=7,
            json=False,
        )

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.doctor._healthy_base_url_or_none"
            ) as mock_base_url,
            patch("cdx_proxy_cli_v2.cli.commands.doctor.fetch_json") as mock_fetch,
            patch(
                "cdx_proxy_cli_v2.cli.commands.doctor._fetch_health_accounts"
            ) as mock_health_accounts,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_fetch.return_value = {
                "probed": 3,
                "results": [
                    {
                        "file": "healthy.json",
                        "previous_status": "OK",
                        "status": "OK",
                        "action": "healthy",
                        "http_status": 200,
                        "latency_ms": 15,
                    },
                    {
                        "file": "rate.json",
                        "previous_status": "OK",
                        "status": "OK",
                        "action": "would_cooldown",
                        "http_status": 429,
                        "latency_ms": 22,
                    },
                    {
                        "file": "auth.json",
                        "previous_status": "OK",
                        "status": "OK",
                        "action": "auth_failed",
                        "http_status": 403,
                        "latency_ms": 31,
                    },
                ],
            }
            mock_health_accounts.return_value = []

            result = handle_doctor(args)

        captured = capsys.readouterr()
        assert result == 0
        assert "Probe outcomes:" in captured.out
        assert (
            "would_cooldown: 1 (Probe hit 429; key would enter cooldown if used live)"
            in captured.out
        )
        assert (
            "auth_failed: 1 (Probe hit 401/403; auth looks unhealthy)" in captured.out
        )
        assert "cdx doctor | probe findings" in captured.out
        assert "Probe outcomes" not in captured.err


def test_state_bucket_treats_warn_as_whitelist():
    assert _state_bucket("WARN") == "whitelist"


class TestHandleAll:
    """Tests for cdx all behavior."""

    def test_handle_all_prefers_runtime_health_when_proxy_is_healthy(
        self, capsys, temp_auth_dir
    ):
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key="mgmt-secret",
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            warn_at=70,
            cooldown_at=90,
            timeout=8,
            only="both",
            json=True,
        )

        with (
            patch("cdx_proxy_cli_v2.cli.commands.all.service_status") as mock_status,
            patch(
                "cdx_proxy_cli_v2.cli.commands.all._fetch_health_accounts"
            ) as mock_fetch_accounts,
            patch(
                "cdx_proxy_cli_v2.cli.commands.all.build_collective_payload"
            ) as mock_fallback,
            patch(
                "cdx_proxy_cli_v2.cli.commands.all._load_codex_auth_identity"
            ) as mock_identity,
        ):
            mock_status.return_value = {
                "healthy": True,
                "base_url": "http://127.0.0.1:8080",
            }
            mock_fetch_accounts.return_value = [
                {"file": "ok.json", "status": "OK", "eligible_now": True, "used": 1},
                {
                    "file": "bad.json",
                    "status": "BLACKLIST",
                    "eligible_now": False,
                    "used": 2,
                },
            ]
            mock_fallback.side_effect = AssertionError("offline fallback should not be used")
            mock_identity.return_value = (None, None, None)

            result = handle_all(args)

        captured = capsys.readouterr()
        assert result == 0
        payload = json.loads(captured.out)
        assert payload["aggregate"]["counts"]["blacklist"] == 1
        assert payload["availability"]["available_now"] == 1
        assert any(item["status"] == "BLACKLIST" for item in payload["accounts"])


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

    def test_settings_from_args_propagates_auto_reset_options(self, temp_auth_dir):
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            auto_reset_on_single_key=True,
            auto_reset_streak=5,
            auto_reset_cooldown=120,
        )

        settings = _settings_from_args(args)

        assert settings.auto_reset_on_single_key is True
        assert settings.auto_reset_streak == 5
        assert settings.auto_reset_cooldown == 120


class TestCliContracts:
    """Tests for user-facing CLI contracts."""

    def test_main_returns_user_error_for_invalid_cli_port(self, capsys):
        result = main(["status", "--port", "70000"])

        captured = capsys.readouterr()
        assert result == 2
        assert "port must be between 0 and 65535" in captured.err

    def test_pyproject_registers_cdx_script_only(self):
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        scripts = data["project"]["scripts"]
        assert scripts == {"cdx": "cdx_proxy_cli_v2.cli.main:main"}


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


class TestHandleRotate:
    """Tests for handle_rotate function."""

    def test_rotate_returns_error_when_proxy_not_healthy(self, capsys, temp_auth_dir):
        """Test rotate fails when proxy is not running."""
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            dry_run=False,
            json=False,
        )

        with patch("cdx_proxy_cli_v2.cli.shared.service_status") as mock_status:
            mock_status.return_value = {
                "healthy": False,
                "base_url": "http://127.0.0.1:8080",
            }
            result = handle_rotate(args)

        captured = capsys.readouterr()
        assert result == 1
        assert "Proxy is not healthy/running" in captured.err

    def test_rotate_no_healthy_auths(self, capsys, temp_auth_dir):
        """Test rotate when no healthy auths available."""
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            dry_run=False,
            json=False,
        )

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._healthy_base_url_or_none"
            ) as mock_base_url,
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
            ) as mock_next_auth,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_next_auth.return_value = None
            result = handle_rotate(args)

        captured = capsys.readouterr()
        assert result == 1
        assert "No healthy auth keys available" in captured.err

    def test_rotate_successful(self, capsys, temp_auth_dir, tmp_path, monkeypatch):
        """Test successful rotation to a healthy auth."""
        # Create auth dir with a healthy auth file
        auth_dir = Path(temp_auth_dir)
        auth_file = auth_dir / "healthy_auth.json"
        auth_data = {
            "email": "test@example.com",
            "tokens": {
                "access_token": "secret_token_123",
                "account_id": "acc_123",
            },
        }
        auth_file.write_text(json.dumps(auth_data))

        # Set up codex home to be a temp directory
        codex_home = tmp_path / ".codex"
        codex_home.mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("CODEX_HOME", raising=False)

        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            dry_run=False,
            json=False,
        )

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._healthy_base_url_or_none"
            ) as mock_base_url,
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
            ) as mock_next_auth,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_next_auth.return_value = {
                "file": "healthy_auth.json",
                "email": "test@example.com",
                "used": 5,
            }
            result = handle_rotate(args)

        captured = capsys.readouterr()
        assert result == 0
        assert "Rotated to auth key: healthy_auth.json" in captured.out
        assert "test@example.com" in captured.out

        # Verify the auth file was written
        dest_path = codex_home / "auth.json"
        assert dest_path.exists()
        written_data = json.loads(dest_path.read_text())
        assert written_data["email"] == "test@example.com"
        assert written_data["tokens"]["access_token"] == "secret_token_123"

    def test_rotate_dry_run(self, capsys, temp_auth_dir):
        """Test rotate --dry-run shows what would happen."""
        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            dry_run=True,
            json=False,
        )

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._healthy_base_url_or_none"
            ) as mock_base_url,
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
            ) as mock_next_auth,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_next_auth.return_value = {
                "file": "auth1.json",
                "email": "user1@example.com",
                "used": 5,
            }
            result = handle_rotate(args)

        captured = capsys.readouterr()
        assert result == 0
        assert "Dry run: Would rotate to auth key" in captured.out
        assert "auth1.json" in captured.out

    def test_rotate_json_output(self, capsys, temp_auth_dir, tmp_path, monkeypatch):
        """Test rotate --json outputs JSON."""
        # Create auth dir with a healthy auth file
        auth_dir = Path(temp_auth_dir)
        auth_file = auth_dir / "auth1.json"
        auth_data = {
            "email": "user1@example.com",
            "tokens": {"access_token": "token123"},
        }
        auth_file.write_text(json.dumps(auth_data))

        codex_home = tmp_path / ".codex"
        codex_home.mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("CODEX_HOME", raising=False)

        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            dry_run=False,
            json=True,
        )

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._healthy_base_url_or_none"
            ) as mock_base_url,
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
            ) as mock_next_auth,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_next_auth.return_value = {
                "file": "auth1.json",
                "email": "user1@example.com",
                "used": 5,
            }
            result = handle_rotate(args)

        captured = capsys.readouterr()
        assert result == 0
        output = json.loads(captured.out)
        assert output["success"] is True
        assert output["selected"]["file"] == "auth1.json"
        assert output["selected"]["email"] == "user1@example.com"

    def test_rotate_uses_runtime_selected_auth(
        self, capsys, temp_auth_dir, tmp_path, monkeypatch
    ):
        """Test rotate trusts the runtime-selected auth instead of sorting locally."""
        # Create auth files
        auth_dir = Path(temp_auth_dir)
        (auth_dir / "auth_new.json").write_text(
            json.dumps({"email": "new@example.com", "tokens": {"access_token": "new"}})
        )
        (auth_dir / "auth_old.json").write_text(
            json.dumps({"email": "old@example.com", "tokens": {"access_token": "old"}})
        )

        codex_home = tmp_path / ".codex"
        codex_home.mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("CODEX_HOME", raising=False)

        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            dry_run=True,
            json=False,
        )

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._healthy_base_url_or_none"
            ) as mock_base_url,
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
            ) as mock_next_auth,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_next_auth.return_value = {
                "file": "auth_old.json",
                "email": "old@example.com",
                "used": 100,
            }
            result = handle_rotate(args)

        captured = capsys.readouterr()
        assert result == 0
        assert "auth_old.json" in captured.out

    def test_rotate_returns_error_when_live_next_auth_fetch_fails(
        self, capsys, temp_auth_dir, tmp_path, monkeypatch
    ):
        auth_dir = Path(temp_auth_dir)
        (auth_dir / "auth_cached.json").write_text(
            json.dumps(
                {
                    "email": "cached@example.com",
                    "tokens": {"access_token": "cached-token"},
                }
            )
        )
        codex_home = tmp_path / ".codex"
        codex_home.mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("CODEX_HOME", raising=False)

        args = argparse.Namespace(
            auth_dir=temp_auth_dir,
            host=None,
            port=None,
            upstream=None,
            management_key=None,
            allow_non_loopback=None,
            trace_max=None,
            request_timeout=None,
            dry_run=False,
            json=False,
        )

        with (
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._healthy_base_url_or_none"
            ) as mock_base_url,
            patch(
                "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
            ) as mock_next_auth,
        ):
            mock_base_url.return_value = "http://127.0.0.1:8080"
            mock_next_auth.side_effect = RuntimeError("timed out")
            result = handle_rotate(args)

        captured = capsys.readouterr()
        assert result == 1
        assert "Failed to fetch next auth selection: timed out" in captured.err


class TestMainHelp:
    def test_main_without_command_prints_help_and_returns_zero(self, capsys):
        result = main([])

        captured = capsys.readouterr()
        assert result == 0
        assert "cdx proxy cli v2" in captured.out
        assert "run-server" not in captured.out

    def test_build_parser_help_hides_run_server(self):
        help_text = build_parser().format_help()

        assert "run-server" not in help_text
        assert "==SUPPRESS==" not in help_text

    def test_build_parser_still_accepts_hidden_run_server(self):
        args = build_parser().parse_args(["run-server"])

        assert args.command == "run-server"
        assert callable(args.handler)
