from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cdx_proxy_cli_v2.proxy.server import (
    CHATGPT_ACCOUNT_MODEL_FALLBACK,
    CHATGPT_ACCOUNT_MODEL_REWRITES,
)

FIVE_HOURS_SECONDS = 5 * 60 * 60
WEEK_SECONDS = 7 * 24 * 60 * 60
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
LOOPBACK_HOST = "127.0.0.1"
RESPONSES_PATH = "/v1/responses"
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
MODELS_PATH = "/models"
OPENAI_MODELS_PATH = "/v1/models"
BACKEND_MODELS_PATH = "/backend-api/models"
TRACE_PATH = "/trace"
HEALTH_PATH = "/health"
DEBUG_PATH = "/debug"
DEFAULT_TEST_MODEL = "gpt-4"
DEFAULT_TEST_MODEL_DISPLAY_NAME = "GPT-4"
DEFAULT_TEST_MINI_MODEL = "gpt-4-mini"
ACCOUNT_INCOMPATIBLE_REQUEST_MODEL = next(iter(CHATGPT_ACCOUNT_MODEL_REWRITES))
ACCOUNT_COMPATIBLE_FALLBACK_MODEL = CHATGPT_ACCOUNT_MODEL_FALLBACK
DEFAULT_TEST_MESSAGE = "Hello"
DEFAULT_TEST_CHAT_MESSAGE = "Hi"
DEFAULT_TEST_INPUT = "hello"


def write_auth(path: Path, token: str, email: str, account_id: str = "") -> None:
    data: Dict[str, object] = {"access_token": token, "email": email}
    if account_id:
        data["account_id"] = account_id
    path.write_text(json.dumps(data), encoding="utf-8")


def request_json(
    *,
    base_url: str,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, object]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 3.0,
) -> Tuple[int, Dict[str, object]]:
    req_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = Request(f"{base_url}{path}", data=data, method=method, headers=req_headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), json.loads(raw) if raw else {}


def make_usage_payload(
    *,
    plan_type: str = "plus",
    five_hour_used_percent: float = 0.0,
    five_hour_reset_after_seconds: int = 3600,
    weekly_used_percent: Optional[float] = None,
    weekly_reset_after_seconds: int = WEEK_SECONDS,
    limit_reached: bool = False,
) -> Dict[str, object]:
    rate_limit: Dict[str, object] = {"limit_reached": limit_reached}
    rate_limit["primary_window"] = {
        "limit_window_seconds": FIVE_HOURS_SECONDS,
        "used_percent": float(five_hour_used_percent),
        "reset_after_seconds": int(five_hour_reset_after_seconds),
    }
    if weekly_used_percent is not None:
        rate_limit["secondary_window"] = {
            "limit_window_seconds": WEEK_SECONDS,
            "used_percent": float(weekly_used_percent),
            "reset_after_seconds": int(weekly_reset_after_seconds),
        }
    return {"plan_type": plan_type, "rate_limit": rate_limit}


def parse_shell_exports(raw: str) -> Dict[str, str]:
    exports: Dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("export ") or "=" not in stripped:
            continue
        payload = stripped[len("export ") :]
        key, value = payload.split("=", 1)
        exports[key.strip()] = value.strip().strip("'").strip('"')
    return exports


def read_management_key(auth_dir: Path) -> str:
    env_path = auth_dir / ".env"
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "CLIPROXY_MANAGEMENT_KEY":
            return value.strip().strip("'").strip('"')
    raise AssertionError(f"management key not found in {env_path}")


def run_cli(
    *args: str,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    full_env["PYTHONPATH"] = (
        f"{SRC}{os.pathsep}{full_env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    )
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "cdx_proxy_cli_v2", *args],
        cwd=str(cwd or ROOT),
        env=full_env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def build_responses_payload(
    *,
    model: str = DEFAULT_TEST_MODEL,
    message_text: str = DEFAULT_TEST_MESSAGE,
    input_text: Optional[str] = None,
    stream: bool = False,
) -> Dict[str, object]:
    payload: Dict[str, object] = {"model": model}
    if input_text is not None:
        payload["input"] = input_text
    else:
        payload["messages"] = [{"role": "user", "content": message_text}]
    if stream:
        payload["stream"] = True
    return payload


def build_chat_completions_payload(
    *,
    model: str = DEFAULT_TEST_MODEL,
    message_text: str = DEFAULT_TEST_CHAT_MESSAGE,
) -> Dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": message_text}],
    }


class MockUpstreamHandler(BaseHTTPRequestHandler):
    responses: list[Dict[str, object]] = []
    call_count: int = 0
    received_headers: list[Dict[str, str]] = []
    usage_payloads: Dict[str, Dict[str, object]] = {}
    default_usage_payload: Dict[str, object] = make_usage_payload()

    @classmethod
    def reset(cls) -> None:
        cls.responses = []
        cls.call_count = 0
        cls.received_headers = []
        cls.usage_payloads = {}
        cls.default_usage_payload = make_usage_payload()

    @classmethod
    def set_usage_payload(cls, token: str, payload: Dict[str, object]) -> None:
        cls.usage_payloads[token] = payload

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _record_request(self) -> Dict[str, str]:
        MockUpstreamHandler.call_count += 1
        headers = {k: str(v) for k, v in self.headers.items()}
        MockUpstreamHandler.received_headers.append(headers)
        return headers

    def _send_json(self, status: int, data: Dict[str, object]) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _usage_payload(self, headers: Dict[str, str]) -> Dict[str, object]:
        auth_header = headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        return MockUpstreamHandler.usage_payloads.get(
            token, MockUpstreamHandler.default_usage_payload
        )

    def do_GET(self) -> None:
        headers = self._record_request()

        if self.path.startswith("/api/codex/usage") or self.path.startswith(
            "/wham/usage"
        ):
            self._send_json(200, self._usage_payload(headers))
            return

        if self.path == MODELS_PATH:
            self._send_json(
                200,
                {
                    "models": [
                        {
                            "slug": DEFAULT_TEST_MODEL,
                            "title": DEFAULT_TEST_MODEL_DISPLAY_NAME,
                        },
                        {"slug": DEFAULT_TEST_MINI_MODEL},
                    ]
                },
            )
            return

        if self.path in {OPENAI_MODELS_PATH, BACKEND_MODELS_PATH}:
            self._send_json(
                200,
                {"data": [{"id": DEFAULT_TEST_MODEL}, {"id": DEFAULT_TEST_MINI_MODEL}]},
            )
            return

        if RESPONSES_PATH in self.path:
            if self.headers.get("Accept") == "text/event-stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                events = [
                    b'data: {"type": "message_start"}\n\n',
                    b'data: {"type": "content_block_delta", "delta": {"text": "Hello"}}\n\n',
                    b'data: {"type": "content_block_delta", "delta": {"text": " World"}}\n\n',
                    b'data: {"type": "message_stop"}\n\n',
                ]
                for event in events:
                    self.wfile.write(event)
                    self.wfile.flush()
                return
            self._send_json(200, {"id": "resp_123", "status": "completed"})
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        self._record_request()
        self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))

        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_json(
                401, {"error": {"code": "invalid_auth", "message": "Missing auth"}}
            )
            return

        if MockUpstreamHandler.responses:
            response = MockUpstreamHandler.responses.pop(0)
            status = int(response.get("status", 200))
            data = response.get("data", {})
            self._send_json(status, data if isinstance(data, dict) else {})
            return

        if RESPONSES_PATH in self.path:
            if self.headers.get("Accept") == "text/event-stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                events = [
                    b'data: {"type": "response.created"}\n\n',
                    b'data: {"type": "response.output_item.added"}\n\n',
                    b'data: {"type": "done"}\n\n',
                ]
                for event in events:
                    self.wfile.write(event)
                    self.wfile.flush()
                return
            self._send_json(
                200,
                {
                    "id": "resp_123",
                    "object": "response",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "text", "text": "Hello!"}],
                        }
                    ],
                },
            )
            return

        if CHAT_COMPLETIONS_PATH in self.path:
            self._send_json(
                200,
                {
                    "id": "chatcmpl_123",
                    "object": "chat.completion",
                    "choices": [
                        {"message": {"role": "assistant", "content": "Hello!"}}
                    ],
                },
            )
            return

        self._send_json(404, {"error": "unknown endpoint"})
