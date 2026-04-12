from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cdx_proxy_cli_v2.cli.commands.rotate import handle_rotate
from cdx_proxy_cli_v2.cli.main import build_parser


@pytest.fixture
def temp_auth_dir(tmp_path: Path) -> str:
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    return str(auth_dir)


def _rotate_args(
    auth_dir: str,
    *,
    dry_run: bool = False,
    fallback: bool = False,
    no_write: bool = False,
    json_output: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        auth_dir=auth_dir,
        host=None,
        port=None,
        upstream=None,
        management_key=None,
        allow_non_loopback=None,
        trace_max=None,
        request_timeout=None,
        dry_run=dry_run,
        fallback=fallback,
        no_write=no_write,
        json=json_output,
    )


def _set_codex_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return codex_home


def test_rotate_skips_write_when_proxy_active(
    capsys, temp_auth_dir: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = _set_codex_home(monkeypatch, tmp_path)
    args = _rotate_args(temp_auth_dir)

    with (
        patch("cdx_proxy_cli_v2.cli.commands.rotate.service_status") as mock_status,
        patch("cdx_proxy_cli_v2.cli.commands.rotate.fetch_json") as mock_fetch_json,
        patch(
            "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
        ) as mock_next_auth,
    ):
        mock_status.return_value = {"healthy": True, "base_url": "http://127.0.0.1:8080"}
        mock_fetch_json.return_value = {"status": "running"}
        mock_next_auth.return_value = {
            "file": "auth1.json",
            "email": "user1@example.com",
            "used": 5,
        }

        result = handle_rotate(args)

    captured = capsys.readouterr()
    assert result == 0
    assert "Proxy is active" in captured.out
    assert "Next recommended key: auth1.json (user1@example.com)" in captured.out
    assert not (codex_home / "auth.json").exists()


def test_rotate_writes_when_proxy_active_with_fallback(
    capsys, temp_auth_dir: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_dir = Path(temp_auth_dir)
    (auth_dir / "auth1.json").write_text(
        json.dumps({"email": "user1@example.com", "tokens": {"access_token": "token123"}})
    )
    codex_home = _set_codex_home(monkeypatch, tmp_path)
    args = _rotate_args(temp_auth_dir, fallback=True)

    with (
        patch("cdx_proxy_cli_v2.cli.commands.rotate.service_status") as mock_status,
        patch("cdx_proxy_cli_v2.cli.commands.rotate.fetch_json") as mock_fetch_json,
        patch(
            "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
        ) as mock_next_auth,
    ):
        mock_status.return_value = {"healthy": True, "base_url": "http://127.0.0.1:8080"}
        mock_fetch_json.return_value = {"status": "running"}
        mock_next_auth.return_value = {
            "file": "auth1.json",
            "email": "user1@example.com",
            "used": 5,
        }

        result = handle_rotate(args)

    captured = capsys.readouterr()
    assert result == 0
    assert "Rotated to auth key: auth1.json" in captured.out
    assert (codex_home / "auth.json").exists()


def test_rotate_writes_when_proxy_inactive(
    capsys, temp_auth_dir: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_dir = Path(temp_auth_dir)
    (auth_dir / "auth1.json").write_text(
        json.dumps({"email": "user1@example.com", "tokens": {"access_token": "token123"}})
    )
    codex_home = _set_codex_home(monkeypatch, tmp_path)
    args = _rotate_args(temp_auth_dir)

    with (
        patch("cdx_proxy_cli_v2.cli.commands.rotate.service_status") as mock_status,
        patch("cdx_proxy_cli_v2.cli.commands.rotate.fetch_json") as mock_fetch_json,
    ):
        mock_status.return_value = {"healthy": False, "base_url": None}
        mock_fetch_json.side_effect = RuntimeError("proxy down")

        result = handle_rotate(args)

    captured = capsys.readouterr()
    assert result == 0
    assert "Rotated to auth key: auth1.json" in captured.out
    assert (codex_home / "auth.json").exists()


def test_rotate_no_write_flag_always_reports(
    capsys, temp_auth_dir: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = _set_codex_home(monkeypatch, tmp_path)
    args = _rotate_args(temp_auth_dir, no_write=True)

    with (
        patch("cdx_proxy_cli_v2.cli.commands.rotate.service_status") as mock_status,
        patch("cdx_proxy_cli_v2.cli.commands.rotate.fetch_json") as mock_fetch_json,
        patch(
            "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
        ) as mock_next_auth,
    ):
        mock_status.return_value = {"healthy": True, "base_url": "http://127.0.0.1:8080"}
        mock_fetch_json.return_value = {"status": "running"}
        mock_next_auth.return_value = {
            "file": "auth1.json",
            "email": "user1@example.com",
            "used": 5,
        }

        result = handle_rotate(args)

    captured = capsys.readouterr()
    assert result == 0
    assert "No-write mode: auth.json was not modified." in captured.out
    assert not (codex_home / "auth.json").exists()


def test_rotate_json_includes_proxy_active_field(
    capsys, temp_auth_dir: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_codex_home(monkeypatch, tmp_path)
    args = _rotate_args(temp_auth_dir, json_output=True)

    with (
        patch("cdx_proxy_cli_v2.cli.commands.rotate.service_status") as mock_status,
        patch("cdx_proxy_cli_v2.cli.commands.rotate.fetch_json") as mock_fetch_json,
        patch(
            "cdx_proxy_cli_v2.cli.commands.rotate._fetch_runtime_next_auth"
        ) as mock_next_auth,
    ):
        mock_status.return_value = {"healthy": True, "base_url": "http://127.0.0.1:8080"}
        mock_fetch_json.return_value = {"status": "running"}
        mock_next_auth.return_value = {
            "file": "auth1.json",
            "email": "user1@example.com",
            "used": 5,
        }

        result = handle_rotate(args)

    captured = capsys.readouterr()
    assert result == 0
    payload = json.loads(captured.out)
    assert payload["proxy_active"] is True
    assert payload["selected"]["file"] == "auth1.json"


def test_build_parser_accepts_rotate_fallback_and_no_write_flags() -> None:
    args = build_parser().parse_args(["rotate", "--fallback", "--no-write"])

    assert args.command == "rotate"
    assert args.fallback is True
    assert args.no_write is True
