"""Singleton process enforcement via PID file locking."""

from __future__ import annotations

import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator, Optional, Tuple

from cdx_proxy_cli_v2.config.settings import resolve_path


class SingletonLockError(RuntimeError):
    """Raised when singleton acquisition fails."""


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


def trace_pid_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "cdx_trace.pid"


def is_expected_trace_process(pid: Optional[int], auth_dir: str) -> bool:
    if not _is_pid_running(pid):
        return False
    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return False
    normalized_auth_dir = str(resolve_path(auth_dir))
    return (
        "cdx_proxy_cli_v2" in cmdline
        and "trace" in cmdline
        and normalized_auth_dir in cmdline
    )


@contextmanager
def singleton_lock(
    pid_path: Path,
    *,
    name: str = "process",
    kill_existing: bool = False,
    process_matches: Optional[Callable[[int], bool]] = None,
) -> Generator[Tuple[bool, Optional[int]], None, None]:
    """Context manager for singleton process enforcement.

    Args:
        pid_path: Path to the PID file
        name: Human-readable name for error messages
        kill_existing: If True, kill existing process; if False, exit with error
        process_matches: Optional verifier for a live PID before replacement

    Yields:
        Tuple of (killed_existing, previous_pid)
    """
    killed_existing = False
    previous_pid: Optional[int] = None

    existing_pid = _read_pid(pid_path)

    if existing_pid is not None and _is_pid_running(existing_pid):
        if kill_existing:
            if process_matches is not None and not process_matches(existing_pid):
                raise SingletonLockError(
                    f"Refusing to replace {name}: PID {existing_pid} does not match the expected process."
                )
            killed_existing = _terminate_pid(existing_pid)
            previous_pid = existing_pid
        else:
            raise SingletonLockError(
                f"Another {name} is already running (PID {existing_pid}). "
                "Use --replace to replace it, or stop it first."
            )

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
