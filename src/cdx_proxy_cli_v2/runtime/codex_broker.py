from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional


BROKER_BUSY_RPC_CODE = -32001


def _send_line(handle, payload: dict[str, Any]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    handle.flush()


def _build_busy_response(message_id: Any) -> dict[str, Any]:
    return {
        "id": message_id,
        "error": {
            "code": BROKER_BUSY_RPC_CODE,
            "message": "Shared Codex broker is busy.",
        },
    }


def _read_json_line(raw_line: str) -> dict[str, Any] | None:
    line = raw_line.strip()
    if not line:
        return None
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


class BrokerServer:
    def __init__(self, *, cwd: Path, socket_path: Path) -> None:
        self.cwd = cwd
        self.socket_path = socket_path
        self.shutdown_event = threading.Event()
        self.active_conn: Optional[socket.socket] = None
        self.active_lock = threading.Lock()

    def _spawn_app_server(self) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ["codex", "app-server"],
            cwd=str(self.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

    def _stderr_pump(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            sys.stderr.write(line)
            sys.stderr.flush()

    def _stdout_pump(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            conn = None
            with self.active_lock:
                conn = self.active_conn
            if conn is None:
                continue
            try:
                conn.sendall(line.encode("utf-8"))
            except OSError:
                with self.active_lock:
                    if self.active_conn is conn:
                        self.active_conn = None
        self.shutdown_event.set()

    def _shutdown(self, proc: subprocess.Popen[str]) -> None:
        self.shutdown_event.set()
        with self.active_lock:
            conn = self.active_conn
            self.active_conn = None
        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
        if proc.poll() is None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except OSError:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass

    def _handle_client(self, conn: socket.socket, proc: subprocess.Popen[str]) -> None:
        with conn:
            reader = conn.makefile("r", encoding="utf-8", newline="\n")
            while not self.shutdown_event.is_set():
                raw_line = reader.readline()
                if raw_line == "":
                    break
                message = _read_json_line(raw_line)
                if message is None:
                    continue
                if message.get("method") == "broker/shutdown":
                    try:
                        conn.sendall(
                            (
                                json.dumps({"id": message.get("id"), "result": {}})
                                + "\n"
                            ).encode("utf-8")
                        )
                    except OSError:
                        pass
                    self._shutdown(proc)
                    return
                with self.active_lock:
                    if self.active_conn is None:
                        self.active_conn = conn
                    elif self.active_conn is not conn:
                        message_id = message.get("id")
                        if message_id is not None:
                            try:
                                conn.sendall(
                                    (
                                        json.dumps(_build_busy_response(message_id))
                                        + "\n"
                                    ).encode("utf-8")
                                )
                            except OSError:
                                pass
                        return
                if proc.stdin is None:
                    return
                try:
                    proc.stdin.write(raw_line)
                    proc.stdin.flush()
                except OSError:
                    self.shutdown_event.set()
                    return
            with self.active_lock:
                if self.active_conn is conn:
                    self.active_conn = None

    def serve(self) -> int:
        proc = self._spawn_app_server()
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        server.listen()
        server.settimeout(0.25)

        stdout_thread = threading.Thread(
            target=self._stdout_pump, args=(proc,), daemon=True
        )
        stderr_thread = threading.Thread(
            target=self._stderr_pump, args=(proc,), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            while not self.shutdown_event.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    if proc.poll() is not None:
                        break
                    continue
                thread = threading.Thread(
                    target=self._handle_client, args=(conn, proc), daemon=True
                )
                thread.start()
                if proc.poll() is not None:
                    break
        finally:
            try:
                server.close()
            finally:
                self._shutdown(proc)
                try:
                    if self.socket_path.exists():
                        self.socket_path.unlink()
                except OSError:
                    pass
        return proc.returncode or 0


def run_broker(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cdx run-codex-broker")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--socket-path", required=True)
    args = parser.parse_args(argv)
    server = BrokerServer(
        cwd=Path(args.cwd).expanduser().resolve(),
        socket_path=Path(args.socket_path).expanduser().resolve(),
    )
    return server.serve()
