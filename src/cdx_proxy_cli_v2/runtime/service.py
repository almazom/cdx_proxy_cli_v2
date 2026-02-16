from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from cdx_proxy_cli_v2.observability.event_log import tail_lines
from cdx_proxy_cli_v2.proxy.http_client import fetch_json
from cdx_proxy_cli_v2.config.settings import (
    ENV_AUTH_DIR,
    ENV_HOST,
    ENV_MANAGEMENT_KEY,
    ENV_PORT,
    ENV_TRACE_MAX,
    ENV_UPSTREAM,
    Settings,
    ensure_management_key,
    resolve_path,
    upsert_env_values,
)

DEFAULT_STARTUP_TIMEOUT_SECONDS = 12.0


@dataclass(frozen=True)
class ServiceStartResult:
    host: str
    port: int
    base_url: str
    management_key: str
    started: bool


def pid_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "rr_proxy_v2.pid"


def state_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "rr_proxy_v2.state.json"


def log_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "rr_proxy_v2.log"


def events_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "rr_proxy_v2.events.jsonl"


def _read_pid(path: Path) -> Optional[int]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        return int(raw)
    except Exception:
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _is_pid_running(pid: Optional[int]) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_pid(pid: Optional[int], timeout_seconds: float = 8.0) -> None:
    if not _is_pid_running(pid):
        return
    assert pid is not None
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + max(0.1, timeout_seconds)
    while time.time() < deadline:
        if not _is_pid_running(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _load_state(path: Path) -> Dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _save_state(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _management_headers(key: Optional[str]) -> Dict[str, str]:
    if not key:
        return {}
    return {"X-Management-Key": key}


def pick_free_port(host: str) -> int:
    infos = socket.getaddrinfo(host, 0, type=socket.SOCK_STREAM)
    family, socktype, proto, _canon, sockaddr = infos[0]
    with socket.socket(family, socktype, proto) as sock:
        sock.bind(sockaddr)
        return int(sock.getsockname()[1])


def probe_debug(base_url: str, management_key: Optional[str]) -> Optional[dict]:
    try:
        payload = fetch_json(
            base_url=base_url,
            path="/debug",
            headers=_management_headers(management_key),
            timeout=0.6,
        )
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _wait_for_ready(base_url: str, management_key: str, timeout_seconds: float) -> Optional[dict]:
    deadline = time.time() + max(0.1, timeout_seconds)
    while time.time() < deadline:
        payload = probe_debug(base_url, management_key)
        if isinstance(payload, dict) and payload.get("status") == "running":
            return payload
        time.sleep(0.12)
    return None


def _spawn(settings: Settings, *, port: int, management_key: str) -> subprocess.Popen[bytes]:
    argv = [
        sys.executable,
        "-m",
        "cdx_proxy_cli_v2",
        "run-server",
        "--auth-dir",
        settings.auth_dir,
        "--host",
        settings.host,
        "--port",
        str(port),
        "--upstream",
        settings.upstream,
        "--management-key",
        management_key,
        "--trace-max",
        str(settings.trace_max),
    ]
    if settings.allow_non_loopback:
        argv.append("--allow-non-loopback")

    log_file = log_path(settings.auth_dir)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env[ENV_AUTH_DIR] = settings.auth_dir
    env[ENV_HOST] = settings.host
    env[ENV_PORT] = str(port)
    env[ENV_UPSTREAM] = settings.upstream
    env[ENV_MANAGEMENT_KEY] = management_key
    env[ENV_TRACE_MAX] = str(settings.trace_max)
    with log_file.open("ab") as handle:
        process = subprocess.Popen(
            argv,
            stdout=handle,
            stderr=handle,
            env=env,
            start_new_session=True,
        )
    return process


def start_service(settings: Settings) -> ServiceStartResult:
    key = ensure_management_key(settings.auth_dir, settings.management_key)
    runtime_settings = settings.with_management_key(key)
    port = runtime_settings.port if runtime_settings.port > 0 else pick_free_port(runtime_settings.host)
    runtime_settings = runtime_settings.with_port(port)

    pid_file = pid_path(runtime_settings.auth_dir)
    state_file = state_path(runtime_settings.auth_dir)
    current_pid = _read_pid(pid_file)
    current_state = _load_state(state_file)

    if _is_pid_running(current_pid):
        state_base_url = str(current_state.get("base_url") or runtime_settings.base_url)
        debug = probe_debug(state_base_url, key)
        if isinstance(debug, dict) and debug.get("status") == "running":
            running_host = str(debug.get("host") or runtime_settings.host)
            running_port = int(debug.get("port") or runtime_settings.port)
            return ServiceStartResult(
                host=running_host,
                port=running_port,
                base_url=f"http://{running_host}:{running_port}",
                management_key=key,
                started=False,
            )
        _terminate_pid(current_pid, timeout_seconds=5.0)

    process = _spawn(runtime_settings, port=runtime_settings.port, management_key=key)
    _write_pid(pid_file, process.pid)

    debug = _wait_for_ready(
        runtime_settings.base_url,
        key,
        timeout_seconds=DEFAULT_STARTUP_TIMEOUT_SECONDS,
    )
    if debug is None:
        _terminate_pid(process.pid, timeout_seconds=3.0)
        _remove_file(pid_file)
        raise RuntimeError(f"proxy failed to start; inspect {log_path(runtime_settings.auth_dir)}")

    payload: Dict[str, object] = {
        "status": "running",
        "updated_at": int(time.time()),
        "pid": process.pid,
        "auth_dir": runtime_settings.auth_dir,
        "host": runtime_settings.host,
        "port": runtime_settings.port,
        "base_url": runtime_settings.base_url,
        "upstream": runtime_settings.upstream,
    }
    _save_state(state_file, payload)
    upsert_env_values(
        runtime_settings.env_path,
        {
            ENV_AUTH_DIR: runtime_settings.auth_dir,
            ENV_HOST: runtime_settings.host,
            ENV_PORT: str(runtime_settings.port),
            ENV_UPSTREAM: runtime_settings.upstream,
            ENV_MANAGEMENT_KEY: key,
            ENV_TRACE_MAX: str(runtime_settings.trace_max),
        },
    )
    return ServiceStartResult(
        host=runtime_settings.host,
        port=runtime_settings.port,
        base_url=runtime_settings.base_url,
        management_key=key,
        started=True,
    )


def stop_service(settings: Settings) -> bool:
    pid_file = pid_path(settings.auth_dir)
    state_file = state_path(settings.auth_dir)
    current_pid = _read_pid(pid_file)
    if not _is_pid_running(current_pid):
        _remove_file(pid_file)
        return False

    state = _load_state(state_file)
    host = str(state.get("host") or settings.host)
    port_raw = state.get("port")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = settings.port
    base_url = f"http://{host}:{port}" if port > 0 else settings.base_url

    key = settings.management_key
    if key:
        try:
            fetch_json(
                base_url=base_url,
                path="/shutdown",
                method="POST",
                headers=_management_headers(key),
                timeout=1.0,
            )
        except Exception:
            pass
    _terminate_pid(current_pid, timeout_seconds=6.0)
    _remove_file(pid_file)
    _save_state(
        state_file,
        {
            "status": "stopped",
            "updated_at": int(time.time()),
            "auth_dir": settings.auth_dir,
            "host": host,
            "port": port,
            "base_url": base_url,
        },
    )
    return True


def service_status(settings: Settings) -> Dict[str, object]:
    state = _load_state(state_path(settings.auth_dir))
    pid = _read_pid(pid_path(settings.auth_dir))
    running_pid = _is_pid_running(pid)

    host = str(state.get("host") or settings.host)
    port_raw = state.get("port")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = settings.port
    base_url = f"http://{host}:{port}" if port > 0 else settings.base_url
    debug = probe_debug(base_url, settings.management_key)
    healthy = bool(isinstance(debug, dict) and debug.get("status") == "running")

    auth_count = None
    if isinstance(debug, dict):
        value = debug.get("auth_count")
        if isinstance(value, int):
            auth_count = value

    return {
        "pid": pid,
        "pid_running": running_pid,
        "healthy": healthy,
        "base_url": base_url,
        "host": host,
        "port": port,
        "auth_count": auth_count,
        "state": state.get("status"),
        "log_file": str(log_path(settings.auth_dir)),
        "events_file": str(events_path(settings.auth_dir)),
    }


def tail_service_logs(auth_dir: str, lines: int = 120) -> list[str]:
    return tail_lines(log_path(auth_dir), limit=lines)
