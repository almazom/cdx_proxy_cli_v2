from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.integration.support import (
    DEBUG_PATH,
    LOOPBACK_HOST,
    TRACE_PATH,
    parse_shell_exports,
    read_management_key,
    request_json,
    run_cli,
    write_auth,
)


def _assert_ok(result: subprocess.CompletedProcess[str], *, label: str) -> None:
    assert result.returncode == 0, f"{label} failed: {result.stderr or result.stdout}"


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _start_proxy(auth_dir: Path, upstream_base_url: str) -> str:
    start = run_cli(
        "proxy",
        "--auth-dir",
        str(auth_dir),
        "--upstream",
        upstream_base_url,
        "--host",
        LOOPBACK_HOST,
        "--port",
        "0",
        "--print-env-only",
        env={"CLIPROXY_USAGE_BASE_URL": upstream_base_url},
    )
    _assert_ok(start, label="cdx proxy")
    exports = parse_shell_exports(start.stdout)
    return exports["CLIPROXY_BASE_URL"]


def _stop_proxy(auth_dir: Path, env: dict[str, str]) -> None:
    stop = run_cli("stop", "--auth-dir", str(auth_dir), env=env)
    _assert_ok(stop, label="cdx stop")


def _write_fake_cdx(tmp_path: Path) -> Path:
    body = f"""#!{sys.executable}
import os
import sys

os.execv(sys.executable, [sys.executable, "-m", "cdx_proxy_cli_v2", *sys.argv[1:]])
"""
    return _write_executable(tmp_path / "fake_cdx", body)


def _write_fake_codex(tmp_path: Path) -> Path:
    body = f"""#!{sys.executable}
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen


def fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def parse_base_url(argv: list[str]) -> str:
    for index, arg in enumerate(argv):
        if arg != "-c" or index + 1 >= len(argv):
            continue
        payload = argv[index + 1]
        if not payload.startswith("openai_base_url="):
            continue
        return payload.split("=", 1)[1].strip().strip('"')
    fail("missing openai_base_url config")
    return ""


def parse_workdir(argv: list[str]) -> str | None:
    for index, arg in enumerate(argv):
        if arg == "-C" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def final_text(prompt: str) -> str:
    if "REQ1 OK" in prompt:
        return "REQ1 OK"
    if "alpha-beta" in prompt:
        Path("proof.txt").write_text("alpha-beta", encoding="utf-8")
        if Path("proof.txt").read_text(encoding="utf-8") != "alpha-beta":
            fail("proof.txt content mismatch")
        return "STEP1 OK\\nSTEP2 OK\\nFILE=alpha-beta"
    if "PROXY CHECK OK" in prompt:
        return "PROXY CHECK OK"
    fail(f"unexpected prompt: {{prompt!r}}")
    return ""


def main() -> int:
    argv = sys.argv[1:]
    if "exec" not in argv:
        fail("expected exec subcommand")
    if "--json" not in argv:
        fail("expected --json")
    if "--dangerously-bypass-approvals-and-sandbox" not in argv:
        fail("missing bypass flag")
    if "OPENAI_BASE_URL" in os.environ:
        fail("OPENAI_BASE_URL should be unset")
    if "OPENAI_API_BASE" in os.environ:
        fail("OPENAI_API_BASE should be unset")

    workdir = parse_workdir(argv)
    if workdir:
        os.chdir(workdir)

    prompt = argv[-1]
    base_url = parse_base_url(argv).rstrip("/")

    req = Request(
        f"{{base_url}}/v1/responses",
        data=json.dumps({{"input": prompt}}).encode("utf-8"),
        method="POST",
        headers={{"Content-Type": "application/json"}},
    )
    with urlopen(req, timeout=10.0) as response:
        if response.status != 200:
            fail(f"unexpected proxy status: {{response.status}}")
        raw = response.read().decode("utf-8")
        payload = json.loads(raw) if raw else {{}}
        if payload.get("status") != "completed":
            fail(f"unexpected proxy payload: {{payload}}")

    text = final_text(prompt)
    print(json.dumps({{"type": "thread.started", "thread_id": "fake-thread"}}))
    print(json.dumps({{"type": "turn.started"}}))
    print(
        json.dumps(
            {{
                "type": "item.completed",
                "item": {{"id": "item_0", "type": "agent_message", "text": text}},
            }}
        )
    )
    print(
        json.dumps(
            {{
                "type": "turn.completed",
                "usage": {{"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}},
            }}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    return _write_executable(tmp_path / "fake_codex", body)


def _cli_env(auth_dir: Path, upstream_base_url: str) -> dict[str, str]:
    return {
        "CLIPROXY_AUTH_DIR": str(auth_dir),
        "CLIPROXY_USAGE_BASE_URL": upstream_base_url,
        "CLIPROXY_MANAGEMENT_KEY": read_management_key(auth_dir),
    }


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _jsonl_slice(path: Path, start_line: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[start_line:] if line.strip()]


def _debug_payload(base_url: str, management_key: str) -> dict[str, Any]:
    status, body = request_json(
        base_url=base_url,
        path=DEBUG_PATH,
        headers={"X-Management-Key": management_key},
    )
    assert status == 200
    return body


def _run_codex_wp(prompt: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(Path("bin/codex_wp")),
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "-C",
            "/tmp",
            prompt,
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        text=True,
        capture_output=True,
        timeout=30.0,
        check=False,
    )


def _parse_json_stream(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _final_message(events: list[dict[str, Any]]) -> str:
    messages = [
        str(item["item"]["text"])
        for item in events
        if item.get("type") == "item.completed"
        and isinstance(item.get("item"), dict)
        and item["item"].get("type") == "agent_message"
    ]
    assert messages
    return messages[-1]


def _assert_json_stream_shape(events: list[dict[str, Any]]) -> None:
    event_types = [str(item.get("type")) for item in events]
    assert "thread.started" in event_types
    assert "turn.started" in event_types
    assert "turn.completed" in event_types
    assert any(event_type == "item.completed" for event_type in event_types)


def test_codex_wp_green_path_verifies_multistep_proxy_flow(
    tmp_path: Path,
    upstream_server: str,
) -> None:
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    write_auth(auth_dir / "a.json", "tok-a", "a@example.com", "acc-a")
    write_auth(auth_dir / "b.json", "tok-b", "b@example.com", "acc-b")

    fake_cdx = _write_fake_cdx(tmp_path)
    fake_codex = _write_fake_codex(tmp_path)

    base_url = _start_proxy(auth_dir, upstream_server)
    env = _cli_env(auth_dir, upstream_server)
    events_file = auth_dir / "rr_proxy_v2.events.jsonl"

    wrapper_env = os.environ.copy()
    wrapper_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    wrapper_env.update(env)
    wrapper_env["CDX_BIN"] = str(fake_cdx)
    wrapper_env["CODEX_BIN"] = str(fake_codex)

    try:
        before_status = run_cli("status", "--json", "--auth-dir", str(auth_dir), env=env)
        _assert_ok(before_status, label="cdx status before")
        before_status_payload = json.loads(before_status.stdout)
        assert before_status_payload["healthy"] is True

        before_doctor = run_cli("doctor", "--json", "--auth-dir", str(auth_dir), env=env)
        _assert_ok(before_doctor, label="cdx doctor before")
        before_doctor_payload = json.loads(before_doctor.stdout)
        assert before_doctor_payload["summary"]["blacklist"] == 0

        requests_before = int(_debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"]["requests_total"])
        events_before = _count_lines(events_file)

        prompts = [
            ("Reply with exactly REQ1 OK and stop.", "REQ1 OK"),
            (
                "Work only in the current directory.\n"
                "1. Create a file named proof.txt containing exactly alpha-beta.\n"
                "2. Read proof.txt.\n"
                "3. Reply with exactly three lines:\n"
                "STEP1 OK\nSTEP2 OK\nFILE=alpha-beta",
                "STEP1 OK\nSTEP2 OK\nFILE=alpha-beta",
            ),
            ("Reply with exactly PROXY CHECK OK and stop.", "PROXY CHECK OK"),
        ]

        seen_request_ids: list[str] = []
        for index, (prompt, expected) in enumerate(prompts, start=1):
            step_events_before = _count_lines(events_file)
            step_requests_before = int(
                _debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"]["requests_total"]
            )

            result = _run_codex_wp(prompt, wrapper_env)
            assert result.returncode == 0, result.stderr or result.stdout

            stream = _parse_json_stream(result.stdout)
            _assert_json_stream_shape(stream)
            assert _final_message(stream) == expected

            step_requests_after = int(
                _debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"]["requests_total"]
            )
            assert step_requests_after - step_requests_before == 1

            delta_events = _jsonl_slice(events_file, step_events_before)
            proxy_events = [
                event
                for event in delta_events
                if event.get("event") == "proxy.request"
            ]
            assert proxy_events, f"missing proxy.request for request {index}"
            assert any(str(event.get("path") or "").endswith("/responses") for event in proxy_events)
            assert any(int(event.get("status", 0)) == 200 for event in proxy_events)

            for event in proxy_events:
                request_id = str(event.get("request_id") or "")
                assert request_id
                seen_request_ids.append(request_id)
                assert int(event.get("attempt", 0)) == 1

        requests_after = int(_debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"]["requests_total"])
        events_after = _count_lines(events_file)
        assert requests_after - requests_before == 3
        assert events_after - events_before >= 3

        trace_status, trace_body = request_json(
            base_url=base_url,
            path=f"{TRACE_PATH}?limit=20",
            headers={"X-Management-Key": env["CLIPROXY_MANAGEMENT_KEY"]},
        )
        assert trace_status == 200
        trace_request_ids = {
            str(event.get("request_id"))
            for event in trace_body["events"]
            if event.get("event") == "proxy.request"
        }
        assert any(request_id in trace_request_ids for request_id in seen_request_ids)

        after_status = run_cli("status", "--json", "--auth-dir", str(auth_dir), env=env)
        _assert_ok(after_status, label="cdx status after")
        after_status_payload = json.loads(after_status.stdout)
        assert after_status_payload["healthy"] is True

        after_doctor = run_cli("doctor", "--json", "--auth-dir", str(auth_dir), env=env)
        _assert_ok(after_doctor, label="cdx doctor after")
        after_doctor_payload = json.loads(after_doctor.stdout)
        assert after_doctor_payload["summary"]["blacklist"] == 0
        assert after_doctor_payload["summary"]["cooldown"] == 0
    finally:
        _stop_proxy(auth_dir, env)
