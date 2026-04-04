from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from cdx_proxy_cli_v2.config.settings import Settings, resolve_path


STATE_SCHEMA_VERSION = "1.0.0"
RUNTIME_DIR_NAME = "codex-runtime"


@dataclass(frozen=True)
class CodexRuntimePaths:
    workspace_root: Path
    runtime_dir: Path
    state_file: Path
    pid_file: Path
    log_file: Path
    socket_file: Path


def _workspace_slug(workspace_root: Path) -> str:
    slug = workspace_root.name or "workspace"
    slug = "".join(char if char.isalnum() or char in "._-" else "-" for char in slug)
    slug = slug.strip("-") or "workspace"
    digest = hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}"


def runtime_paths(auth_dir: str, cwd: str | Path) -> CodexRuntimePaths:
    workspace_root = Path(cwd).expanduser().resolve()
    runtime_dir = resolve_path(auth_dir) / RUNTIME_DIR_NAME / _workspace_slug(workspace_root)
    return CodexRuntimePaths(
        workspace_root=workspace_root,
        runtime_dir=runtime_dir,
        state_file=runtime_dir / "runtime.json",
        pid_file=runtime_dir / "broker.pid",
        log_file=runtime_dir / "broker.log",
        socket_file=runtime_dir / "broker.sock",
    )


def _load_state(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    schema_version = raw.get("$schema_version", STATE_SCHEMA_VERSION)
    if schema_version != STATE_SCHEMA_VERSION:
        return {}
    return raw


def _save_state(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    enriched = {
        "$schema_version": STATE_SCHEMA_VERSION,
        "$written_at": int(time.time()),
        **payload,
    }
    path.write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")


def _read_pid(path: Path) -> Optional[int]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def _is_pid_running(pid: Optional[int]) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _terminate_pid(pid: Optional[int], timeout_seconds: float = 5.0) -> None:
    if not _is_pid_running(pid):
        return
    assert pid is not None
    try:
        os.kill(pid, 15)
    except OSError:
        return
    deadline = time.time() + max(0.1, timeout_seconds)
    while time.time() < deadline:
        if not _is_pid_running(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, 9)
    except OSError:
        return


def _read_process_cmdline(pid: Optional[int]) -> Optional[str]:
    if pid is None:
        return None
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        raw = proc_cmdline.read_bytes()
    except OSError:
        raw = b""
    if raw:
        return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    cmdline = result.stdout.strip()
    return cmdline or None


def _matches_runtime_process(pid: Optional[int], paths: CodexRuntimePaths) -> bool:
    if not _is_pid_running(pid):
        return False
    cmdline = _read_process_cmdline(pid) or ""
    return (
        "cdx_proxy_cli_v2" in cmdline
        and "run-codex-broker" in cmdline
        and str(paths.workspace_root) in cmdline
    )


def _socket_ready(socket_path: Path, timeout_seconds: float = 0.5) -> bool:
    if not socket_path.exists():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    try:
        sock.connect(str(socket_path))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _cleanup_stale(paths: CodexRuntimePaths) -> None:
    pid = _read_pid(paths.pid_file)
    if _is_pid_running(pid) and _matches_runtime_process(pid, paths):
        return
    _terminate_pid(pid)
    _remove_file(paths.pid_file)
    _remove_file(paths.socket_file)


def _spawn_runtime(paths: CodexRuntimePaths) -> subprocess.Popen[bytes]:
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-m",
        "cdx_proxy_cli_v2",
        "run-codex-broker",
        "--cwd",
        str(paths.workspace_root),
        "--socket-path",
        str(paths.socket_file),
    ]
    with paths.log_file.open("ab") as handle:
        return subprocess.Popen(
            argv,
            stdout=handle,
            stderr=handle,
            start_new_session=True,
        )


def _wait_for_socket(paths: CodexRuntimePaths, timeout_seconds: float = 10.0) -> bool:
    deadline = time.time() + max(0.1, timeout_seconds)
    while time.time() < deadline:
        if _socket_ready(paths.socket_file):
            return True
        time.sleep(0.1)
    return False


def ensure_codex_runtime(
    settings: Settings, cwd: str | Path
) -> Dict[str, Any]:
    paths = runtime_paths(settings.auth_dir, cwd)
    state = _load_state(paths.state_file)
    pid = _read_pid(paths.pid_file)

    if _matches_runtime_process(pid, paths) and _socket_ready(paths.socket_file):
        payload = {
            "workspace_root": str(paths.workspace_root),
            "state": "running",
            "endpoint": str(paths.socket_file),
            "pid": pid,
            "log_file": str(paths.log_file),
            "started": False,
            "reused": True,
        }
        _save_state(paths.state_file, payload)
        return payload

    _cleanup_stale(paths)
    process = _spawn_runtime(paths)
    _write_pid(paths.pid_file, process.pid)

    if not _wait_for_socket(paths):
        _terminate_pid(process.pid)
        _remove_file(paths.pid_file)
        raise RuntimeError(
            f"codex runtime broker failed to start for {paths.workspace_root}; inspect {paths.log_file}"
        )

    payload = {
        "workspace_root": str(paths.workspace_root),
        "state": "running",
        "endpoint": str(paths.socket_file),
        "pid": process.pid,
        "log_file": str(paths.log_file),
        "started": True,
        "reused": False,
    }
    _save_state(paths.state_file, payload)
    return payload


def codex_runtime_status(settings: Settings, cwd: str | Path) -> Dict[str, Any]:
    paths = runtime_paths(settings.auth_dir, cwd)
    state = _load_state(paths.state_file)
    pid = _read_pid(paths.pid_file)
    pid_running = _matches_runtime_process(pid, paths)
    healthy = pid_running and _socket_ready(paths.socket_file)
    status = "running" if healthy else str(state.get("state") or "stopped")
    return {
        "workspace_root": str(paths.workspace_root),
        "state": status,
        "endpoint": str(paths.socket_file) if paths.socket_file.exists() else None,
        "pid": pid,
        "pid_running": pid_running,
        "healthy": healthy,
        "log_file": str(paths.log_file),
        "state_file": str(paths.state_file),
    }


def stop_codex_runtime(settings: Settings, cwd: str | Path) -> bool:
    paths = runtime_paths(settings.auth_dir, cwd)
    pid = _read_pid(paths.pid_file)
    stopped = False
    if paths.socket_file.exists():
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.connect(str(paths.socket_file))
            sock.sendall(
                (
                    json.dumps({"id": 1, "method": "broker/shutdown", "params": {}})
                    + "\n"
                ).encode("utf-8")
            )
            try:
                sock.recv(1024)
            except OSError:
                pass
            stopped = True
        except OSError:
            stopped = False
        finally:
            sock.close()
    _terminate_pid(pid)
    _remove_file(paths.pid_file)
    _remove_file(paths.socket_file)
    _save_state(
        paths.state_file,
        {
            "workspace_root": str(paths.workspace_root),
            "state": "stopped",
            "endpoint": str(paths.socket_file),
            "pid": None,
            "log_file": str(paths.log_file),
            "started": False,
            "reused": False,
        },
    )
    return stopped or bool(pid)
