"""Tests for runtime singleton helpers."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cdx_proxy_cli_v2.runtime.singleton import (
    SingletonLockError,
    is_expected_trace_process,
    singleton_lock,
)


def test_is_expected_trace_process_matches_trace_cmdline(tmp_path: Path) -> None:
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    pid = 4242
    cmdline = (
        f"/usr/bin/python3 -m cdx_proxy_cli_v2 trace --auth-dir {auth_dir} --limit 20"
    )

    with (
        patch("cdx_proxy_cli_v2.runtime.singleton._is_pid_running", return_value=True),
        patch(
            "cdx_proxy_cli_v2.runtime.singleton._read_process_cmdline",
            return_value=cmdline,
        ),
    ):
        assert is_expected_trace_process(pid, str(auth_dir)) is True
        assert is_expected_trace_process(pid, str(auth_dir.parent / "other")) is False


def test_singleton_lock_removes_stale_pid_and_cleans_up(tmp_path: Path) -> None:
    pid_path = tmp_path / "cdx_trace.pid"
    pid_path.write_text("4242", encoding="utf-8")

    with patch("cdx_proxy_cli_v2.runtime.singleton._is_pid_running", return_value=False):
        with singleton_lock(pid_path, name="cdx trace") as (killed_existing, previous_pid):
            assert killed_existing is False
            assert previous_pid is None
            assert pid_path.read_text(encoding="utf-8") == str(os.getpid())

    assert not pid_path.exists()


def test_singleton_lock_blocks_existing_process_without_replace(tmp_path: Path) -> None:
    pid_path = tmp_path / "cdx_trace.pid"
    pid_path.write_text("4242", encoding="utf-8")

    with patch("cdx_proxy_cli_v2.runtime.singleton._is_pid_running", return_value=True):
        with pytest.raises(
            SingletonLockError,
            match="Another cdx trace is already running",
        ):
            with singleton_lock(pid_path, name="cdx trace"):
                pass

    assert pid_path.read_text(encoding="utf-8") == "4242"


def test_singleton_lock_rejects_unverified_replacement(tmp_path: Path) -> None:
    pid_path = tmp_path / "cdx_trace.pid"
    pid_path.write_text("4242", encoding="utf-8")

    with (
        patch("cdx_proxy_cli_v2.runtime.singleton._is_pid_running", return_value=True),
        patch("cdx_proxy_cli_v2.runtime.singleton._terminate_pid") as mock_terminate,
    ):
        with pytest.raises(
            SingletonLockError,
            match="does not match the expected process",
        ):
            with singleton_lock(
                pid_path,
                name="cdx trace",
                kill_existing=True,
                process_matches=lambda pid: False,
            ):
                pass

    mock_terminate.assert_not_called()
    assert pid_path.read_text(encoding="utf-8") == "4242"


def test_singleton_lock_replaces_verified_process(tmp_path: Path) -> None:
    pid_path = tmp_path / "cdx_trace.pid"
    pid_path.write_text("4242", encoding="utf-8")

    with (
        patch("cdx_proxy_cli_v2.runtime.singleton._is_pid_running", return_value=True),
        patch("cdx_proxy_cli_v2.runtime.singleton._terminate_pid", return_value=True) as mock_terminate,
    ):
        with singleton_lock(
            pid_path,
            name="cdx trace",
            kill_existing=True,
            process_matches=lambda pid: True,
        ) as (killed_existing, previous_pid):
            assert killed_existing is True
            assert previous_pid == 4242
            assert pid_path.read_text(encoding="utf-8") == str(os.getpid())

    mock_terminate.assert_called_once_with(4242)
    assert not pid_path.exists()
