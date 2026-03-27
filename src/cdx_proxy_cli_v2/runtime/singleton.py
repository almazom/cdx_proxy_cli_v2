"""Singleton process enforcement via PID file locking."""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Tuple

from cdx_proxy_cli_v2.config.settings import resolve_path


def _read_pid(path: Path) -> Optional[int]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_pid(pid: int, timeout_steps: int = 10) -> bool:
    """Terminate a process. Returns True if killed, False if already gone."""
    try:
        os.kill(pid, 15)  # SIGTERM
        for _ in range(timeout_steps):
            if not _is_pid_running(pid):
                return True
            time.sleep(0.1)
        os.kill(pid, 9)  # SIGKILL
        time.sleep(0.1)
        return True
    except OSError:
        return False


def trace_pid_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "cdx_trace.pid"


@contextmanager
def singleton_lock(
    pid_path: Path,
    *,
    name: str = "process",
    kill_existing: bool = False,
) -> Generator[Tuple[bool, Optional[int]], None, None]:
    """Context manager for singleton process enforcement.

    Args:
        pid_path: Path to the PID file
        name: Human-readable name for error messages
        kill_existing: If True, kill existing process; if False, exit with error

    Yields:
        Tuple of (killed_existing, previous_pid)
    """
    killed_existing = False
    previous_pid: Optional[int] = None

    existing_pid = _read_pid(pid_path)

    if existing_pid is not None and _is_pid_running(existing_pid):
        if kill_existing:
            killed_existing = _terminate_pid(existing_pid)
            previous_pid = existing_pid
        else:
            print(f"Error: Another {name} is already running (PID {existing_pid})", file=sys.stderr)
            print("Use --replace to replace it, or stop it first.", file=sys.stderr)
            sys.exit(1)

    if existing_pid is not None and not _is_pid_running(existing_pid):
        try:
            pid_path.unlink(missing_ok=True)
        except Exception:
            pass

    _write_pid(pid_path, os.getpid())

    try:
        yield (killed_existing, previous_pid)
    finally:
        if _read_pid(pid_path) == os.getpid():
            try:
                pid_path.unlink(missing_ok=True)
            except Exception:
                pass
