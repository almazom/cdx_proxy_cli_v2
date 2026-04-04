from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cdx_proxy_cli_v2.config.settings import build_settings
from cdx_proxy_cli_v2.runtime.codex_runtime import (
    STATE_SCHEMA_VERSION,
    codex_runtime_status,
    ensure_codex_runtime,
    runtime_paths,
    stop_codex_runtime,
    _load_state,
    _save_state,
)


@pytest.fixture
def temp_auth_dir(tmp_path: Path) -> str:
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    return str(auth_dir)


def test_runtime_state_round_trip(tmp_path: Path) -> None:
    state_file = tmp_path / "runtime.json"
    _save_state(state_file, {"state": "running", "pid": 123})
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["$schema_version"] == STATE_SCHEMA_VERSION
    loaded = _load_state(state_file)
    assert loaded["state"] == "running"


def test_ensure_codex_runtime_reuses_existing_runtime(temp_auth_dir: str, monkeypatch) -> None:
    monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
    settings = build_settings()
    paths = runtime_paths(settings.auth_dir, ".")
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pid_file.write_text(str(os.getpid()), encoding="utf-8")
    paths.socket_file.write_text("", encoding="utf-8")

    with patch(
        "cdx_proxy_cli_v2.runtime.codex_runtime._matches_runtime_process",
        return_value=True,
    ), patch(
        "cdx_proxy_cli_v2.runtime.codex_runtime._socket_ready",
        return_value=True,
    ):
        payload = ensure_codex_runtime(settings, ".")

    assert payload["reused"] is True
    assert payload["started"] is False


def test_ensure_codex_runtime_spawns_when_missing(temp_auth_dir: str, monkeypatch) -> None:
    monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
    settings = build_settings()

    with patch(
        "cdx_proxy_cli_v2.runtime.codex_runtime._matches_runtime_process",
        return_value=False,
    ), patch(
        "cdx_proxy_cli_v2.runtime.codex_runtime._socket_ready",
        side_effect=[False, True],
    ), patch(
        "cdx_proxy_cli_v2.runtime.codex_runtime._spawn_runtime"
    ) as mock_spawn:
        mock_proc = MagicMock()
        mock_proc.pid = 43210
        mock_spawn.return_value = mock_proc
        payload = ensure_codex_runtime(settings, ".")

    assert payload["started"] is True
    assert payload["reused"] is False
    assert payload["pid"] == 43210


def test_codex_runtime_status_reports_stopped(temp_auth_dir: str, monkeypatch) -> None:
    monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
    settings = build_settings()

    payload = codex_runtime_status(settings, ".")

    assert payload["state"] == "stopped"
    assert payload["healthy"] is False


def test_stop_codex_runtime_persists_stopped_state(temp_auth_dir: str, monkeypatch) -> None:
    monkeypatch.setenv("CLIPROXY_AUTH_DIR", temp_auth_dir)
    settings = build_settings()
    paths = runtime_paths(settings.auth_dir, ".")
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pid_file.write_text(str(os.getpid()), encoding="utf-8")
    paths.socket_file.write_text("", encoding="utf-8")

    with patch(
        "cdx_proxy_cli_v2.runtime.codex_runtime._terminate_pid"
    ) as mock_terminate:
        stopped = stop_codex_runtime(settings, ".")

    assert stopped is True
    mock_terminate.assert_called()
    state = _load_state(paths.state_file)
    assert state["state"] == "stopped"
