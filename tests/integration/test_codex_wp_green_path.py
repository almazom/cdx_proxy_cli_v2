from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from cdx_proxy_cli_v2.config.settings import (
    ENV_CODEX_WP_ZELLIJ_AUTO_NAME,
    ENV_CODEX_WP_ZELLIJ_FLOAT_CLOSE_ON_EXIT,
    ENV_CODEX_WP_ZELLIJ_FLOAT_HEIGHT,
    ENV_CODEX_WP_ZELLIJ_FLOAT_NAME,
    ENV_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX,
    ENV_CODEX_WP_ZELLIJ_FLOAT_RIGHT,
    ENV_CODEX_WP_ZELLIJ_FLOAT_TOP,
    ENV_CODEX_WP_ZELLIJ_FLOAT_WIDTH,
    ENV_CODEX_WP_ZELLIJ_TITLE_CASE,
    ENV_CODEX_WP_ZELLIJ_TITLE_FALLBACK,
    ENV_CODEX_WP_ZELLIJ_TITLE_MAX_WORDS,
)
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

ROOT = Path(__file__).resolve().parents[2]


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


def _write_fake_proxy_env_cdx(tmp_path: Path) -> Path:
    body = f"""#!{sys.executable}
import sys

if sys.argv[1:] == ["proxy", "--print-env-only"]:
    print('export CLIPROXY_BASE_URL="http://127.0.0.1:43123"')
    raise SystemExit(0)

print(f"unexpected fake cdx argv: {{sys.argv[1:]!r}}", file=sys.stderr)
raise SystemExit(97)
"""
    return _write_executable(tmp_path / "fake_cdx_proxy_env", body)


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
    if "Use $auto-commit." in prompt:
        return "Auto-commit shortcut OK"
    if "Use $code-simplifier." in prompt:
        return "Code-simplifier shortcut OK"
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
    json_mode = "--json" in argv
    if "--help" in argv or (argv and argv[0] == "help"):
        if "review" in argv:
            print("Fake Codex Review Help")
            print("Usage: codex review [OPTIONS]")
        elif "exec" in argv:
            print("Fake Codex Exec Help")
            print("Usage: codex exec [OPTIONS] [PROMPT] [COMMAND]")
        else:
            print("Fake Codex CLI Help")
            print("Usage: codex [OPTIONS] [PROMPT]")
        print("  -p, --profile <CONFIG_PROFILE>")
        return 0

    if "exec" not in argv:
        fail("expected exec subcommand")
    prompt = argv[-1]
    log_path = os.environ.get("FAKE_CODEX_LOG_PATH", "")
    if log_path:
        with Path(log_path).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({{"prompt": prompt}}) + "\\n")
    is_fixed_shortcut_prompt = (
        "Use $auto-commit." in prompt or "Use $code-simplifier." in prompt
    )
    if not is_fixed_shortcut_prompt and not json_mode:
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

    fail_match = os.environ.get("FAKE_CODEX_FAIL_MATCH", "")
    if fail_match and fail_match in prompt:
        fail(f"forced failure for prompt containing {{fail_match!r}}", code=1)

    if not is_fixed_shortcut_prompt:
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
    if json_mode:
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
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    return _write_executable(tmp_path / "fake_codex", body)


def _write_fake_hook_codex(tmp_path: Path) -> Path:
    body = f"""#!{sys.executable}
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def parse_workdir(argv: list[str]) -> str | None:
    for index, arg in enumerate(argv):
        if arg == "-C" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def append_log(record: dict[str, object]) -> None:
    log_path = os.environ.get("FAKE_HOOK_CODEX_LOG_PATH", "")
    if not log_path:
        return
    with Path(log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\\n")


def session_file_for(home: Path, session_id: str) -> Path:
    session_dir = home / ".codex" / "sessions" / "2026" / "03" / "29"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / f"rollout-fake-{{session_id}}.jsonl"


def next_turn_number(session_file: Path) -> int:
    if not session_file.exists():
        return 1
    turns = 0
    for line in session_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("type") == "turn_context":
            turns += 1
    return turns + 1


def write_session_event(
    session_file: Path,
    *,
    session_id: str,
    turn: int,
    prompt: str,
    text: str,
) -> None:
    lines: list[dict[str, object]] = []
    if not session_file.exists():
        lines.append(
            {{
                "type": "session_meta",
                "payload": {{"id": session_id, "source": "exec", "originator": "codex_exec"}},
            }}
        )
    lines.append(
        {{
            "type": "turn_context",
            "payload": {{"session_id": session_id, "turn_id": f"turn-{{turn}}"}},
        }}
    )
    lines.append(
        {{
            "type": "event_msg",
            "payload": {{"role": "user", "content": prompt}},
        }}
    )
    lines.append(
        {{
            "type": "event_msg",
            "payload": {{"role": "assistant", "content": text}},
        }}
    )
    with session_file.open("a", encoding="utf-8") as handle:
        for payload in lines:
            handle.write(json.dumps(payload) + "\\n")

def print_json_events(session_id: str, turn: int, text: str) -> None:
    if os.environ.get("FAKE_HOOK_CODEX_EMIT_WEIRD_JSON") == "1":
        print("[]")
        print(json.dumps({{"type": "session_meta", "payload": []}}))
        print(json.dumps({{"type": "event_msg", "payload": []}}))
        print(json.dumps({{"type": "item.completed", "item": "oops"}}))
    print(json.dumps({{"type": "session_meta", "payload": {{"id": session_id, "source": "exec"}}}}))
    print(json.dumps({{"type": "thread.started", "thread_id": session_id}}))
    print(json.dumps({{"type": "turn.started"}}))
    print(
        json.dumps(
            {{
                "type": "event_msg",
                "payload": {{"role": "assistant", "content": text}},
            }}
        )
    )
    print(
        json.dumps(
            {{
                "type": "item.completed",
                "item": {{"id": f"item_{{turn}}", "type": "agent_message", "text": text}},
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


def main() -> int:
    argv = sys.argv[1:]
    if "--help" in argv or (argv and argv[0] == "help"):
        if "exec" in argv and "resume" in argv:
            print("Fake Codex Exec Resume Help")
            print("Usage: codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]")
        elif "exec" in argv:
            print("Fake Codex Exec Help")
            print("Usage: codex exec [OPTIONS] [PROMPT] [COMMAND]")
        else:
            print("Fake Codex CLI Help")
            print("Usage: codex [OPTIONS] [PROMPT]")
        print("  -p, --profile <CONFIG_PROFILE>")
        return 0

    if "--dangerously-bypass-approvals-and-sandbox" not in argv:
        fail("missing bypass flag")
    if "OPENAI_BASE_URL" in os.environ:
        fail("OPENAI_BASE_URL should be unset")
    if "OPENAI_API_BASE" in os.environ:
        fail("OPENAI_API_BASE should be unset")

    workdir = parse_workdir(argv)
    if workdir:
        os.chdir(workdir)

    home = Path(os.environ.get("HOME", str(Path.home())))

    if "exec" not in argv and "e" not in argv:
        prompt = argv[-1] if argv and not argv[-1].startswith("-") else ""
        append_log({{"mode": "interactive", "argv": argv, "prompt": prompt}})
        if prompt:
            print("Interactive OK")
        return 0

    json_mode = "--json" in argv
    if not json_mode:
        fail("expected --json")

    is_resume = "resume" in argv
    if is_resume:
        session_id = argv[-2]
        prompt = argv[-1]
    else:
        session_id = os.environ.get("FAKE_HOOK_CODEX_SESSION_ID", "fake-hook-session-0001")
        prompt = argv[-1]

    session_file = session_file_for(home, session_id)
    turn = next_turn_number(session_file)

    append_log(
        {{
            "mode": "resume" if is_resume else "exec",
            "argv": argv,
            "prompt": prompt,
            "session_id": session_id,
            "turn": turn,
        }}
    )

    fail_on_turn = os.environ.get("FAKE_HOOK_CODEX_FAIL_ON_TURN", "")
    if fail_on_turn and int(fail_on_turn) == turn:
        fail(f"forced hook failure on turn {{turn}}", code=1)

    text = os.environ.get("FAKE_HOOK_CODEX_MESSAGE_PREFIX", "Hook reply")
    text = f"{{text}} {{turn}}: {{prompt}}"

    write_session_event(
        session_file,
        session_id=session_id,
        turn=turn,
        prompt=prompt,
        text=text,
    )
    print_json_events(session_id, turn, text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    return _write_executable(tmp_path / "fake_hook_codex", body)


def _write_fake_cdx_hook(tmp_path: Path) -> Path:
    body = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

log_path = Path(os.environ["FAKE_CDX_HOOK_LOG_PATH"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"argv": sys.argv[1:]}}) + "\\n")
"""
    return _write_executable(tmp_path / "cdx-hook", body)


def _write_fake_t2me(tmp_path: Path) -> Path:
    body = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

log_path = Path(os.environ["FAKE_T2ME_LOG_PATH"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"argv": sys.argv[1:]}}) + "\\n")
"""
    return _write_executable(tmp_path / "t2me", body)


def _write_fake_extract_intent(tmp_path: Path) -> Path:
    body = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

log_path = os.environ.get("FAKE_EXTRACT_INTENT_LOG_PATH")
if log_path:
    with Path(log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({{"argv": sys.argv[1:]}}) + "\\n")

print(os.environ.get("FAKE_EXTRACT_INTENT_TEXT", "🧭 Intent\\n① fake"))
"""
    return _write_executable(tmp_path / "extract-intent_cli", body)


def _write_fake_zellij(tmp_path: Path) -> tuple[Path, Path]:
    capture_path = tmp_path / "fake_zellij.jsonl"
    body = f"""#!{sys.executable}
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


capture_path = Path(os.environ["FAKE_ZELLIJ_CAPTURE_PATH"])
with capture_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"argv": sys.argv[1:]}}) + "\\n")

argv = sys.argv[1:]
if argv[:2] == ["action", "list-tabs"] and "--json" in argv:
    sys.stdout.write(os.environ.get("FAKE_ZELLIJ_LIST_TABS_STDOUT", "[]"))
    sys.stderr.write(os.environ.get("FAKE_ZELLIJ_LIST_TABS_STDERR", ""))
    raise SystemExit(int(os.environ.get("FAKE_ZELLIJ_LIST_TABS_EXIT", "0")))

if argv[:2] == ["action", "new-tab"]:
    sys.stdout.write(os.environ.get("FAKE_ZELLIJ_NEW_TAB_STDOUT", "5"))
    sys.stderr.write(os.environ.get("FAKE_ZELLIJ_NEW_TAB_STDERR", ""))
    raise SystemExit(int(os.environ.get("FAKE_ZELLIJ_NEW_TAB_EXIT", "0")))

if argv[:2] == ["action", "rename-pane"]:
    sys.stdout.write(os.environ.get("FAKE_ZELLIJ_RENAME_PANE_STDOUT", ""))
    sys.stderr.write(os.environ.get("FAKE_ZELLIJ_RENAME_PANE_STDERR", ""))
    raise SystemExit(int(os.environ.get("FAKE_ZELLIJ_RENAME_PANE_EXIT", "0")))

if argv[:1] == ["run"]:
    run_count = 0
    for line in capture_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if list(json.loads(line)["argv"])[:1] == ["run"]:
            run_count += 1
    suffix = str(run_count)
    run_stdout = (
        os.environ.get(f"FAKE_ZELLIJ_RUN_STDOUT_{{suffix}}")
        or os.environ.get("FAKE_ZELLIJ_RUN_STDOUT", "terminal_11")
    )
    run_stderr = (
        os.environ.get(f"FAKE_ZELLIJ_RUN_STDERR_{{suffix}}")
        or os.environ.get("FAKE_ZELLIJ_RUN_STDERR", "")
    )
    if (
        os.environ.get(f"FAKE_ZELLIJ_RUN_EXECUTE_{{suffix}}")
        or os.environ.get("FAKE_ZELLIJ_RUN_EXECUTE")
    ):
        separator_index = argv.index("--")
        inner_argv = argv[separator_index + 1 :]
        inner_env = os.environ.copy()
        inner_env["ZELLIJ_PANE_ID"] = run_stdout
        subprocess.run(
            inner_argv,
            env=inner_env,
            text=True,
            capture_output=True,
            check=False,
        )
    sys.stdout.write(run_stdout)
    sys.stderr.write(run_stderr)
    raise SystemExit(
        int(
            os.environ.get(f"FAKE_ZELLIJ_RUN_EXIT_{{suffix}}")
            or os.environ.get("FAKE_ZELLIJ_RUN_EXIT", "0")
        )
    )

print(f"unexpected fake zellij argv: {{argv!r}}", file=sys.stderr)
raise SystemExit(97)
"""
    return _write_executable(tmp_path / "zellij", body), capture_path


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


def _run_codex_wp_args(
    args: list[str],
    env: dict[str, str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "bin/codex_wp"), *args],
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=30.0,
        check=False,
    )


def _run_codex_wp(prompt: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run_codex_wp_args(
        [
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "-C",
            "/tmp",
            prompt,
        ],
        env,
    )


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def _fixed_shortcut_prompt(name: str) -> str:
    prompts = {
        "auto_commit": """Use $auto-commit.
Run the full auto-commit skill workflow for the current repository.
Commit everything currently relevant in git status using atomic commits.
Run the fitting checks before committing.
Scan diffs for secrets.
Push if a remote already exists.
Report briefly in simplified Russian.""",
        "code_simplifier": """Use $code-simplifier.
Run a narrow simplification pass for the current repository.
Focus first on currently modified or recently touched code.
If the repository is clean, still run a narrow relevant simplification pass instead of a wide repo rewrite.
Preserve behavior exactly.
Keep edits tight and readable.
Run relevant tests after changes.
Report only significant simplifications.""",
    }
    return prompts[name]


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


def _read_fake_zellij_calls(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    return [
        list(json.loads(line)["argv"])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_fake_codex_prompts(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        str(json.loads(line)["prompt"])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _active_zellij_tab_stdout() -> str:
    return json.dumps(
        [
            {
                "name": "Tab #1",
                "active": True,
                "viewport_columns": 140,
                "viewport_rows": 42,
            }
        ]
    )


def _zellij_env(
    tmp_path: Path,
    capture_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env["FAKE_ZELLIJ_CAPTURE_PATH"] = str(capture_path)
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}".rstrip(os.pathsep)
    if extra_env:
        env.update(extra_env)
    return env


def _path_env(
    tmp_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}".rstrip(os.pathsep)
    if extra_env:
        env.update(extra_env)
    return env


def _extract_new_tab_payload(path: Path) -> list[str]:
    calls = _read_fake_zellij_calls(path)
    assert calls[0] == ["action", "list-tabs", "--json"]
    assert calls[1][:2] == ["action", "new-tab"]
    return calls[1]


def _extract_run_payload(path: Path) -> tuple[list[str], list[str]]:
    calls = _read_fake_zellij_calls(path)
    assert calls[0][:2] == ["action", "list-tabs"]
    assert "--json" in calls[0]
    assert calls[1][:1] == ["run"]
    return calls[0], calls[1]


def _extract_rename_pane_payload(path: Path) -> list[str]:
    calls = _read_fake_zellij_calls(path)
    assert any(call[:2] == ["action", "rename-pane"] for call in calls)
    return next(call for call in calls if call[:2] == ["action", "rename-pane"])


def _extract_close_pane_payload(path: Path) -> list[str]:
    calls = _read_fake_zellij_calls(path)
    assert any(call[:2] == ["action", "close-pane"] for call in calls)
    return next(call for call in calls if call[:2] == ["action", "close-pane"])


def _extract_pair_run_payloads(
    path: Path,
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    calls = _read_fake_zellij_calls(path)
    assert calls[0][:2] == ["action", "list-tabs"]
    assert "--json" in calls[0]
    run_calls = [call for call in calls if call[:1] == ["run"]]
    rename_calls = [call for call in calls if call[:2] == ["action", "rename-pane"]]
    assert len(run_calls) == 2
    assert len(rename_calls) == 2
    return calls[0], run_calls[0], run_calls[1], rename_calls[0], rename_calls[1]


@pytest.mark.parametrize(
    ("args", "expected_usage"),
    [
        (["-F", "--help"], "Usage: codex [OPTIONS] [PROMPT]"),
        (["--zellij-floating", "--help"], "Usage: codex [OPTIONS] [PROMPT]"),
        (["--zellij-new-tab", "--help"], "Usage: codex [OPTIONS] [PROMPT]"),
        (["--zellij-floating-pair", "--help"], "Usage: codex [OPTIONS] [PROMPT]"),
        (["--pair-layout", "stacked", "--help"], "Usage: codex [OPTIONS] [PROMPT]"),
        (["review", "--help"], "Usage: codex review [OPTIONS]"),
    ],
)
def test_codex_wp_help_is_side_effect_free_and_includes_wrapper_help(
    tmp_path: Path,
    args: list[str],
    expected_usage: str,
) -> None:
    _write_fake_zellij(tmp_path)
    fake_codex = _write_fake_codex(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={"CODEX_BIN": str(fake_codex)},
    )

    result = _run_codex_wp_args(args, env)

    assert result.returncode == 0, result.stderr
    assert "codex_wp wrapper flags" in result.stdout
    assert "Help is side-effect free." in result.stdout
    assert (
        "  -SA                          run built-in code-simplifier, then auto-commit"
        in result.stdout
    )
    assert "  -A                           run built-in auto-commit" in result.stdout
    assert (
        "  -S                           run built-in code-simplifier" in result.stdout
    )
    assert "  --hook-times <n>             how many stop events per session (requires --hook stop)" in result.stdout
    assert "  --hook-time <n>              legacy alias for --hook-times" in result.stdout
    assert "  --hook-target <target>       override Telegram target for notifications" in result.stdout
    assert expected_usage in result.stdout
    assert _read_fake_zellij_calls(capture_path) == []


@pytest.mark.parametrize(
    ("args", "expected_stderr"),
    [
        (
            ["exec", "--json", "hello", "--hook-prompt", "resume"],
            "--hook-prompt, --hook-times, --hook-target, and --hook-extract-intent require --hook stop.",
        ),
        (
            ["exec", "--json", "hello", "--hook", "resume"],
            "--hook only supports 'stop'.",
        ),
        (
            ["exec", "--json", "hello", "--hook", "stop"],
            "--hook stop requires --hook-prompt.",
        ),
        (
            ["exec", "--json", "hello", "--hook", "stop", "--hook-prompt", "resume"],
            "--hook stop requires --hook-times.",
        ),
        (
            ["exec", "--json", "hello", "--hook", "stop", "--hook-prompt", "resume", "--hook-times", "0"],
            "--hook-times must be a positive integer.",
        ),
        (
            [
                "--zellij-new-tab",
                "hook-tab",
                "exec",
                "--json",
                "hello",
                "--hook",
                "stop",
                "--hook-prompt",
                "resume",
                "--hook-times",
                "1",
            ],
            "--hook is not supported with zellij launch modes yet.",
        ),
    ],
)
def test_codex_wp_hook_validation_fails_early(
    tmp_path: Path,
    args: list[str],
    expected_stderr: str,
) -> None:
    result = _run_codex_wp_args(args, _path_env(tmp_path))

    assert result.returncode == 2
    assert expected_stderr in result.stderr


@pytest.mark.parametrize(
    ("args", "expected_stderr"),
    [
        (
            ["exec", "hello", "--hook", "stop", "--hook-prompt", "resume", "--hook-times", "2"],
            "headless --hook stop requires 'exec --json'",
        ),
        (
            [
                "exec",
                "--json",
                "--ephemeral",
                "hello",
                "--hook",
                "stop",
                "--hook-prompt",
                "resume",
                "--hook-times",
                "2",
            ],
            "headless --hook stop does not support --ephemeral",
        ),
        (
            [
                "exec",
                "resume",
                "--json",
                "fake-session",
                "hello",
                "--hook",
                "stop",
                "--hook-prompt",
                "resume",
                "--hook-times",
                "2",
            ],
            "does not support manual 'exec resume'",
        ),
    ],
)
def test_codex_wp_headless_hook_preconditions(
    tmp_path: Path,
    args: list[str],
    expected_stderr: str,
) -> None:
    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    fake_codex = _write_fake_hook_codex(tmp_path)
    env = _path_env(
        tmp_path,
        extra_env={
            "CDX_BIN": str(fake_cdx),
            "CODEX_BIN": str(fake_codex),
            "HOME": str(tmp_path / "home"),
        },
    )

    result = _run_codex_wp_args(args, env)

    assert result.returncode == 2
    assert expected_stderr in result.stderr


@pytest.mark.parametrize("extract_intent", [False, True])
def test_codex_wp_interactive_hook_activation_forwards_expected_args(
    tmp_path: Path,
    extract_intent: bool,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    hook_log = tmp_path / "cdx-hook.jsonl"

    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    fake_codex = _write_fake_hook_codex(tmp_path)
    _write_fake_cdx_hook(tmp_path)

    env = _path_env(
        tmp_path,
        extra_env={
            "CDX_BIN": str(fake_cdx),
            "CODEX_BIN": str(fake_codex),
            "FAKE_CDX_HOOK_LOG_PATH": str(hook_log),
            "HOME": str(tmp_path / "home"),
        },
    )

    args = [
        "hello interactive",
        "--hook",
        "stop",
        "--hook-prompt",
        "resume work",
        "--hook-times",
        "2",
        "--hook-target",
        "@ops",
    ]
    if extract_intent:
        args.append("--hook-extract-intent")

    result = _run_codex_wp_args(args, env, cwd=project)

    assert result.returncode == 0, result.stderr
    records = _read_jsonl_records(hook_log)
    assert len(records) == 1
    argv = list(records[0]["argv"])
    assert argv[:2] == ["stop", "on"]
    assert "--project" in argv
    assert str(project) in argv
    assert "--mode" in argv and "resume" in argv
    assert "--ask" in argv and "resume work" in argv
    assert "--times" in argv and "2" in argv
    assert "--target" in argv and "@ops" in argv
    assert ("--extract-intent" in argv) is extract_intent


def test_codex_wp_headless_hook_loop_runs_and_notifies(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    codex_log = tmp_path / "hook-codex.jsonl"
    t2me_log = tmp_path / "t2me.jsonl"
    extract_intent_log = tmp_path / "extract-intent.jsonl"

    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    fake_codex = _write_fake_hook_codex(tmp_path)
    _write_fake_t2me(tmp_path)
    _write_fake_extract_intent(tmp_path)

    env = _path_env(
        tmp_path,
        extra_env={
            "CDX_BIN": str(fake_cdx),
            "CODEX_BIN": str(fake_codex),
            "FAKE_HOOK_CODEX_LOG_PATH": str(codex_log),
            "FAKE_T2ME_LOG_PATH": str(t2me_log),
            "FAKE_EXTRACT_INTENT_LOG_PATH": str(extract_intent_log),
            "FAKE_EXTRACT_INTENT_TEXT": "🧭 Intent\\n① fake step",
            "HOME": str(home),
        },
    )

    result = _run_codex_wp_args(
        [
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-C",
            str(project),
            "first headless prompt",
            "--hook",
            "stop",
            "--hook-prompt",
            "resume again",
            "--hook-times",
            "3",
            "--hook-target",
            "@ops",
            "--hook-extract-intent",
        ],
        env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr

    codex_records = _read_jsonl_records(codex_log)
    assert len(codex_records) == 3
    assert [record["mode"] for record in codex_records] == ["exec", "resume", "resume"]
    assert codex_records[0]["prompt"] == "first headless prompt"
    assert codex_records[1]["prompt"] == "resume again"
    assert codex_records[2]["prompt"] == "resume again"
    session_ids = {str(record["session_id"]) for record in codex_records}
    assert len(session_ids) == 1

    notification_records = _read_jsonl_records(t2me_log)
    assert len(notification_records) == 3
    for record in notification_records:
        assert record["argv"][:3] == ["send", "--target", "@ops"]
    messages = [str(record["argv"][-1]) for record in notification_records]
    assert "🚆🪪🔟 TRAIN-" in messages[0]
    assert "🚃 wagon 1/3" in messages[0]
    assert "🚃 wagon 2/3" in messages[1]
    assert "🚃 wagon 3/3" in messages[2]
    assert "1/3" in messages[0]
    assert "2/3" in messages[1]
    assert "3/3" in messages[2]
    assert "🧭 Intent" in messages[0]
    assert "▶ resume: resume again" in messages[0]
    assert "🏁 Codex Exec Complete" in messages[2]
    assert "✅ all 3 iterations complete" in messages[2]
    session_id = next(iter(session_ids))
    for message in messages:
        assert session_id in message

    session_files = list((home / ".codex" / "sessions").rglob("*.jsonl"))
    assert len(session_files) == 1

    extract_intent_records = _read_jsonl_records(extract_intent_log)
    assert len(extract_intent_records) == 3
    for record in extract_intent_records:
        argv = list(record["argv"])
        assert argv[:3] == ["--input", str(session_files[0]), "--pretty"]
        assert "--processing-provider" in argv and "pi" in argv
        assert "--preflight-timeout" in argv and "30" in argv
        assert "--runtime-timeout" in argv and "300" in argv

    session_text = session_files[0].read_text(encoding="utf-8")
    assert session_id in session_text
    assert "turn_context" in session_text
    assert not (tmp_path / "cdx-hook.jsonl").exists()


def test_codex_wp_headless_hook_loop_tolerates_non_dict_json_variants(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    codex_log = tmp_path / "hook-codex.jsonl"
    t2me_log = tmp_path / "t2me.jsonl"

    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    fake_codex = _write_fake_hook_codex(tmp_path)
    _write_fake_t2me(tmp_path)

    env = _path_env(
        tmp_path,
        extra_env={
            "CDX_BIN": str(fake_cdx),
            "CODEX_BIN": str(fake_codex),
            "FAKE_HOOK_CODEX_LOG_PATH": str(codex_log),
            "FAKE_HOOK_CODEX_EMIT_WEIRD_JSON": "1",
            "FAKE_T2ME_LOG_PATH": str(t2me_log),
            "HOME": str(home),
        },
    )

    result = _run_codex_wp_args(
        [
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-C",
            str(project),
            "first headless prompt",
            "--hook",
            "stop",
            "--hook-prompt",
            "resume again",
            "--hook-time",
            "2",
            "--hook-target",
            "@ops",
        ],
        env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr

    codex_records = _read_jsonl_records(codex_log)
    assert len(codex_records) == 2
    session_ids = {str(record["session_id"]) for record in codex_records}
    assert len(session_ids) == 1

    notification_records = _read_jsonl_records(t2me_log)
    assert len(notification_records) == 2
    messages = [str(record["argv"][-1]) for record in notification_records]
    assert "🚆🪪🔟 TRAIN-" in messages[0]
    assert "🚃 wagon 1/2" in messages[0]
    assert "🚃 wagon 2/2" in messages[1]
    assert "Hook reply 1: first headless prompt" in messages[0]
    assert "Hook reply 2: resume again" in messages[1]
    session_id = next(iter(session_ids))
    for message in messages:
        assert session_id in message


def test_codex_wp_headless_hook_loop_aborts_on_resume_failure(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    codex_log = tmp_path / "hook-codex.jsonl"
    t2me_log = tmp_path / "t2me.jsonl"

    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    fake_codex = _write_fake_hook_codex(tmp_path)
    _write_fake_t2me(tmp_path)

    env = _path_env(
        tmp_path,
        extra_env={
            "CDX_BIN": str(fake_cdx),
            "CODEX_BIN": str(fake_codex),
            "FAKE_HOOK_CODEX_LOG_PATH": str(codex_log),
            "FAKE_HOOK_CODEX_FAIL_ON_TURN": "2",
            "FAKE_T2ME_LOG_PATH": str(t2me_log),
            "HOME": str(home),
        },
    )

    result = _run_codex_wp_args(
        [
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-C",
            str(project),
            "first headless prompt",
            "--hook",
            "stop",
            "--hook-prompt",
            "resume again",
            "--hook-times",
            "3",
        ],
        env,
        cwd=project,
    )

    assert result.returncode == 1

    codex_records = _read_jsonl_records(codex_log)
    assert len(codex_records) == 2
    assert [record["turn"] for record in codex_records] == [1, 2]

    notification_records = _read_jsonl_records(t2me_log)
    assert len(notification_records) == 2
    first_message = str(notification_records[0]["argv"][-1])
    second_message = str(notification_records[1]["argv"][-1])
    assert "🚆🪪🔟 TRAIN-" in first_message
    assert "🚃 wagon 1/3" in first_message
    assert "🚃 wagon 2/3" in second_message
    assert "1/3" in first_message
    assert "Codex Exec FAILED" in second_message
    assert "iteration 2 of 3" in second_message


@pytest.mark.parametrize(
    ("args", "expected_usage"),
    [
        (
            ["exec", "-p", "test-profile", "--help"],
            "Usage: codex exec [OPTIONS] [PROMPT] [COMMAND]",
        ),
        (
            ["review", "-p", "test-profile", "--help"],
            "Usage: codex review [OPTIONS]",
        ),
    ],
)
def test_codex_wp_preserves_upstream_profile_flag_in_help_mode(
    tmp_path: Path,
    args: list[str],
    expected_usage: str,
) -> None:
    _write_fake_zellij(tmp_path)
    fake_codex = _write_fake_codex(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={"CODEX_BIN": str(fake_codex)},
    )

    result = _run_codex_wp_args(args, env)

    assert result.returncode == 0, result.stderr
    assert expected_usage in result.stdout
    assert "-p, --profile <CONFIG_PROFILE>" in result.stdout
    assert "unexpected argument" not in result.stderr
    assert _read_fake_zellij_calls(capture_path) == []


@pytest.mark.parametrize("shortcut_flag", ["-SA", "-A", "-S"])
def test_codex_wp_fixed_shortcuts_reject_additional_arguments(
    tmp_path: Path,
    shortcut_flag: str,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    env = _zellij_env(tmp_path, capture_path)

    result = _run_codex_wp_args([shortcut_flag, "extra"], env)

    assert result.returncode == 2
    assert (
        f"codex_wp: {shortcut_flag} does not accept additional arguments."
        in result.stderr
    )
    assert _read_fake_zellij_calls(capture_path) == []


@pytest.mark.parametrize(
    ("shortcut_flag", "expected_message"),
    [
        ("-SA", "codex_wp: -SA requires a git repository."),
        ("-A", "codex_wp: -A requires a git repository."),
        ("-S", "codex_wp: -S requires a git repository."),
    ],
)
def test_codex_wp_fixed_shortcuts_require_git_repo(
    tmp_path: Path,
    shortcut_flag: str,
    expected_message: str,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    env = _zellij_env(tmp_path, capture_path)

    result = _run_codex_wp_args([shortcut_flag], env, cwd=repo)

    assert result.returncode == 2
    assert expected_message in result.stderr
    assert _read_fake_zellij_calls(capture_path) == []


def test_codex_wp_auto_commit_shortcut_skips_clean_repo(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    env = _zellij_env(tmp_path, capture_path)

    result = _run_codex_wp_args(["-A"], env, cwd=repo)

    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip()
        == "codex_wp: nothing to commit in the current repository."
    )
    assert _read_fake_zellij_calls(capture_path) == []


def test_codex_wp_simplify_then_commit_shortcut_closes_pane_on_success(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    prompt_log_path = tmp_path / "fake_codex_prompts.jsonl"
    fake_codex = _write_fake_codex(tmp_path)
    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "CODEX_BIN": str(fake_codex),
            "CDX_BIN": str(fake_cdx),
            "FAKE_CODEX_LOG_PATH": str(prompt_log_path),
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": _active_zellij_tab_stdout(),
            "FAKE_ZELLIJ_RUN_EXECUTE_1": "1",
        },
    )

    result = _run_codex_wp_args(["-SA"], env, cwd=repo)

    _list_tabs_call, run_call = _extract_run_payload(capture_path)
    close_pane_call = _extract_close_pane_payload(capture_path)
    separator_index = run_call.index("--")
    inner_command = run_call[separator_index + 1 :]

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "terminal_11"
    assert run_call[:9] == [
        "run",
        "--floating",
        "--pinned",
        "true",
        "--cwd",
        str(repo),
        "--name",
        "cdx: Simplify + Commit",
        "--x",
    ]
    assert inner_command[:2] == ["bash", "-lc"]
    assert "Use $code-simplifier." in inner_command[2]
    assert "Use $auto-commit." in inner_command[2]
    assert "codex_wp: -SA simplification failed; leaving floating pane open." in inner_command[2]
    assert "codex_wp: -SA auto-commit failed; leaving floating pane open." in inner_command[2]
    assert close_pane_call == ["action", "close-pane", "--pane-id", "terminal_11"]
    assert _read_fake_codex_prompts(prompt_log_path) == [
        _fixed_shortcut_prompt("code_simplifier"),
        _fixed_shortcut_prompt("auto_commit"),
    ]


def test_codex_wp_simplify_then_commit_shortcut_closes_pane_when_nothing_to_commit(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    prompt_log_path = tmp_path / "fake_codex_prompts.jsonl"
    fake_codex = _write_fake_codex(tmp_path)
    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "CODEX_BIN": str(fake_codex),
            "CDX_BIN": str(fake_cdx),
            "FAKE_CODEX_LOG_PATH": str(prompt_log_path),
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": _active_zellij_tab_stdout(),
            "FAKE_ZELLIJ_RUN_EXECUTE_1": "1",
        },
    )

    result = _run_codex_wp_args(["-SA"], env, cwd=repo)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "terminal_11"
    assert _extract_close_pane_payload(capture_path) == [
        "action",
        "close-pane",
        "--pane-id",
        "terminal_11",
    ]
    assert _read_fake_codex_prompts(prompt_log_path) == [
        _fixed_shortcut_prompt("code_simplifier"),
    ]


@pytest.mark.parametrize(
    ("shortcut_flag", "dirty_repo", "prompt_fragment", "expected_name"),
    [
        ("-A", True, "Use $auto-commit.", "cdx: Auto Commit"),
        ("-S", False, "Use $code-simplifier.", "cdx: Code Simplifier"),
    ],
)
def test_codex_wp_fixed_shortcuts_close_pane_on_success(
    tmp_path: Path,
    shortcut_flag: str,
    dirty_repo: bool,
    prompt_fragment: str,
    expected_name: str,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    fake_codex = _write_fake_codex(tmp_path)
    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    if dirty_repo:
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "CODEX_BIN": str(fake_codex),
            "CDX_BIN": str(fake_cdx),
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": _active_zellij_tab_stdout(),
            "FAKE_ZELLIJ_RUN_EXECUTE_1": "1",
        },
    )

    result = _run_codex_wp_args([shortcut_flag], env, cwd=repo)

    _list_tabs_call, run_call = _extract_run_payload(capture_path)
    close_pane_call = _extract_close_pane_payload(capture_path)
    separator_index = run_call.index("--")
    inner_command = run_call[separator_index + 1 :]

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "terminal_11"
    assert "--close-on-exit" not in run_call
    assert run_call[:9] == [
        "run",
        "--floating",
        "--pinned",
        "true",
        "--cwd",
        str(repo),
        "--name",
        expected_name,
        "--x",
    ]
    assert inner_command[:2] == ["bash", "-lc"]
    assert prompt_fragment in inner_command[2]
    assert 'zellij action close-pane --pane-id "$ZELLIJ_PANE_ID"' in inner_command[2]
    assert close_pane_call == ["action", "close-pane", "--pane-id", "terminal_11"]


@pytest.mark.parametrize(
    ("shortcut_flag", "dirty_repo", "prompt_fragment"),
    [
        ("-A", True, "Use $auto-commit."),
        ("-S", False, "Use $code-simplifier."),
    ],
)
def test_codex_wp_fixed_shortcuts_keep_pane_open_on_failure(
    tmp_path: Path,
    shortcut_flag: str,
    dirty_repo: bool,
    prompt_fragment: str,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    fake_codex = _write_fake_codex(tmp_path)
    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    if dirty_repo:
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "CODEX_BIN": str(fake_codex),
            "CDX_BIN": str(fake_cdx),
            "FAKE_CODEX_FAIL_MATCH": prompt_fragment,
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": _active_zellij_tab_stdout(),
            "FAKE_ZELLIJ_RUN_EXECUTE_1": "1",
        },
    )

    result = _run_codex_wp_args([shortcut_flag], env, cwd=repo)

    calls = _read_fake_zellij_calls(capture_path)
    run_call = next(call for call in calls if call[:1] == ["run"])

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "terminal_11"
    assert prompt_fragment in run_call[run_call.index("--") + 3]
    assert not any(call[:2] == ["action", "close-pane"] for call in calls)


@pytest.mark.parametrize(
    ("fail_match", "expected_prompts"),
    [
        ("Use $code-simplifier.", ["code_simplifier"]),
        ("Use $auto-commit.", ["code_simplifier", "auto_commit"]),
    ],
)
def test_codex_wp_simplify_then_commit_shortcut_keeps_pane_open_on_failure(
    tmp_path: Path,
    fail_match: str,
    expected_prompts: list[str],
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    prompt_log_path = tmp_path / "fake_codex_prompts.jsonl"
    fake_codex = _write_fake_codex(tmp_path)
    fake_cdx = _write_fake_proxy_env_cdx(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "CODEX_BIN": str(fake_codex),
            "CDX_BIN": str(fake_cdx),
            "FAKE_CODEX_FAIL_MATCH": fail_match,
            "FAKE_CODEX_LOG_PATH": str(prompt_log_path),
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": _active_zellij_tab_stdout(),
            "FAKE_ZELLIJ_RUN_EXECUTE_1": "1",
        },
    )

    result = _run_codex_wp_args(["-SA"], env, cwd=repo)

    calls = _read_fake_zellij_calls(capture_path)
    run_call = next(call for call in calls if call[:1] == ["run"])

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "terminal_11"
    assert "Use $code-simplifier." in run_call[run_call.index("--") + 3]
    assert "Use $auto-commit." in run_call[run_call.index("--") + 3]
    assert not any(call[:2] == ["action", "close-pane"] for call in calls)
    assert _read_fake_codex_prompts(prompt_log_path) == [
        _fixed_shortcut_prompt(name) for name in expected_prompts
    ]


def test_codex_wp_zellij_dry_run_prints_resolved_layout_and_command(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    inner_cwd = tmp_path / "inner"
    inner_cwd.mkdir()

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={"FAKE_ZELLIJ_LIST_TABS_STDOUT": "[]"},
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-123",
            "--zellij-template",
            "three-horizontal",
            "--zellij-dry-run",
            "exec",
            "--json",
            "-C",
            str(inner_cwd),
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    expected_layout = ROOT / "layouts/zellij/three-horizontal.kdl"
    expected_command = (
        f"command=zellij action new-tab --name review-123 --cwd {inner_cwd} "
        f"--layout {expected_layout} -- {ROOT / 'bin/codex_wp'} exec --json -C {inner_cwd} "
        "Reply\\ with\\ exactly\\ REQ1\\ OK\\ and\\ stop."
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f"layout={expected_layout}", expected_command]
    assert _read_fake_zellij_calls(capture_path) == [["action", "list-tabs", "--json"]]


def test_codex_wp_zellij_launch_strips_wrapper_flags_from_inner_command(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={"FAKE_ZELLIJ_LIST_TABS_STDOUT": "[]"},
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-42",
            "--zellij-template",
            "single",
            "--zellij-cwd",
            "/tmp/workspace",
            "exec",
            "--json",
            "--ephemeral",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    call = _extract_new_tab_payload(capture_path)
    separator_index = call.index("--")
    inner_command = call[separator_index + 1 :]

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "5"
    assert call[:8] == [
        "action",
        "new-tab",
        "--name",
        "review-42",
        "--cwd",
        "/tmp/workspace",
        "--layout",
        str(ROOT / "layouts/zellij/single.kdl"),
    ]
    assert inner_command == [
        str(ROOT / "bin/codex_wp"),
        "exec",
        "--json",
        "--ephemeral",
        "Reply with exactly REQ1 OK and stop.",
    ]
    assert not any(arg.startswith("--zellij-") for arg in inner_command)


def test_codex_wp_zellij_cwd_uses_explicit_override_before_inner_C(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={"FAKE_ZELLIJ_LIST_TABS_STDOUT": "[]"},
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-explicit",
            "--zellij-cwd",
            "/tmp/explicit",
            "exec",
            "-C",
            "/tmp/from-inner",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    call = _extract_new_tab_payload(capture_path)
    assert result.returncode == 0, result.stderr
    assert call[4:6] == ["--cwd", "/tmp/explicit"]


def test_codex_wp_zellij_cwd_falls_back_to_inner_C(tmp_path: Path) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={"FAKE_ZELLIJ_LIST_TABS_STDOUT": "[]"},
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-inner",
            "exec",
            "-C",
            "/tmp/from-inner",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    call = _extract_new_tab_payload(capture_path)
    assert result.returncode == 0, result.stderr
    assert call[4:6] == ["--cwd", "/tmp/from-inner"]


def test_codex_wp_zellij_cwd_falls_back_to_process_workdir(tmp_path: Path) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    launch_cwd = tmp_path / "launch"
    launch_cwd.mkdir()

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={"FAKE_ZELLIJ_LIST_TABS_STDOUT": "[]"},
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-pwd",
            "exec",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
        cwd=launch_cwd,
    )

    call = _extract_new_tab_payload(capture_path)
    assert result.returncode == 0, result.stderr
    assert call[4:6] == ["--cwd", str(launch_cwd)]


def test_codex_wp_zellij_unknown_template_lists_available_keys(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(tmp_path, capture_path)

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-missing-template",
            "--zellij-template",
            "does-not-exist",
            "exec",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    assert result.returncode == 2
    assert (
        "codex_wp: unknown zellij template 'does-not-exist'. "
        "Valid templates: single, three-horizontal, three-vertical." in result.stderr
    )
    assert _read_fake_zellij_calls(capture_path) == []


def test_codex_wp_zellij_requires_tab_name_when_mode_is_requested(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(tmp_path, capture_path)

    result = _run_codex_wp_args(
        [
            "--zellij-template",
            "single",
            "exec",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    assert result.returncode == 2
    assert (
        "codex_wp: --zellij-new-tab is required when using zellij mode."
        in result.stderr
    )
    assert _read_fake_zellij_calls(capture_path) == []


def test_codex_wp_zellij_requires_an_active_session(tmp_path: Path) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_EXIT": "1",
            "FAKE_ZELLIJ_LIST_TABS_STDERR": "not inside zellij",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-no-session",
            "exec",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    assert result.returncode == 1
    assert "codex_wp: no active zellij session found." in result.stderr
    assert _read_fake_zellij_calls(capture_path) == [["action", "list-tabs", "--json"]]


def test_codex_wp_zellij_duplicate_tab_name_fails_safely(tmp_path: Path) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [{"name": "review-duplicate"}, {"name": "other-tab"}]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "review-duplicate",
            "exec",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    assert result.returncode == 1
    assert "codex_wp: zellij tab 'review-duplicate' already exists." in result.stderr
    assert _read_fake_zellij_calls(capture_path) == [["action", "list-tabs", "--json"]]


def test_codex_wp_zellij_floating_dry_run_uses_default_preset(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-dry-run",
            "exec",
            "--json",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    expected_command = (
        "command=zellij run --floating --pinned true --cwd /home/pets/TOOLS/cdx_proxy_cli_v2 "
        "--name cdx:\\ REQ1\\ Check --x 81 --y 5 --width 56 --height 15 -- "
        "/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec --json "
        "Reply\\ with\\ exactly\\ REQ1\\ OK\\ and\\ stop."
    )

    calls = _read_fake_zellij_calls(capture_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "floating=top=12% right=2% width=40% height=35% close_on_exit=false",
        expected_command,
    ]
    assert calls == [["action", "list-tabs", "--json", "--state", "--dimensions"]]


def test_codex_wp_file_refs_follow_exec_options_in_floating_dry_run(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    context_file = tmp_path / "plan.md"
    context_file.write_text("# plan\n", encoding="utf-8")

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-dry-run",
            "-f",
            str(context_file),
            "exec",
            "--ephemeral",
            "-C",
            "/tmp/pilot",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    expected_command = (
        "command=zellij run --floating --pinned true --cwd /tmp/pilot "
        "--name cdx:\\ REQ1\\ Check --x 81 --y 5 --width 56 --height 15 -- "
        f"{ROOT / 'bin/codex_wp'} exec --ephemeral -C /tmp/pilot "
        f"@{context_file}\\ Reply\\ with\\ exactly\\ REQ1\\ OK\\ and\\ stop."
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "floating=top=12% right=2% width=40% height=35% close_on_exit=false",
        expected_command,
    ]
    assert _read_fake_zellij_calls(capture_path) == [
        ["action", "list-tabs", "--json", "--state", "--dimensions"]
    ]


def test_codex_wp_short_floating_flag_matches_long_flag_in_dry_run(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "-F",
            "--zellij-dry-run",
            "exec",
            "--json",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    expected_command = (
        "command=zellij run --floating --pinned true --cwd /home/pets/TOOLS/cdx_proxy_cli_v2 "
        "--name cdx:\\ REQ1\\ Check --x 81 --y 5 --width 56 --height 15 -- "
        "/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec --json "
        "Reply\\ with\\ exactly\\ REQ1\\ OK\\ and\\ stop."
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "floating=top=12% right=2% width=40% height=35% close_on_exit=false",
        expected_command,
    ]
    assert _read_fake_zellij_calls(capture_path) == [
        ["action", "list-tabs", "--json", "--state", "--dimensions"]
    ]


def test_codex_wp_zellij_floating_launch_derives_x_from_right_padding(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 120,
                        "viewport_rows": 40,
                    }
                ]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-right",
            "3",
            "--zellij-top",
            "4",
            "--zellij-width",
            "48",
            "--zellij-height",
            "16",
            "exec",
            "--json",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    list_tabs_call, run_call = _extract_run_payload(capture_path)
    rename_call = _extract_rename_pane_payload(capture_path)
    separator_index = run_call.index("--")
    inner_command = run_call[separator_index + 1 :]

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "terminal_11"
    assert "--state" in list_tabs_call
    assert "--dimensions" in list_tabs_call
    assert run_call[:17] == [
        "run",
        "--floating",
        "--pinned",
        "true",
        "--cwd",
        str(ROOT),
        "--name",
        "cdx:",
        "--x",
        "69",
        "--y",
        "4",
        "--width",
        "48",
        "--height",
        "16",
        "--",
    ]
    assert "--close-on-exit" not in run_call
    assert inner_command == [
        str(ROOT / "bin/codex_wp"),
        "exec",
        "--json",
        "Reply with exactly REQ1 OK and stop.",
    ]
    assert rename_call == [
        "action",
        "rename-pane",
        "--pane-id",
        "terminal_11",
        "cdx: REQ1 Check",
    ]


def test_codex_wp_zellij_floating_close_on_exit_is_explicit(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-close-on-exit",
            "exec",
            "--json",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    _list_tabs_call, run_call = _extract_run_payload(capture_path)
    rename_call = _extract_rename_pane_payload(capture_path)
    assert result.returncode == 0, result.stderr
    assert run_call[:9] == [
        "run",
        "--floating",
        "--close-on-exit",
        "--pinned",
        "true",
        "--cwd",
        str(ROOT),
        "--name",
        "cdx:",
    ]
    assert rename_call == [
        "action",
        "rename-pane",
        "--pane-id",
        "terminal_11",
        "cdx: REQ1 Check",
    ]


def test_codex_wp_zellij_floating_conflicts_with_new_tab_mode(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(tmp_path, capture_path)

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-new-tab",
            "review-tab",
            "exec",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    assert result.returncode == 2
    assert (
        "codex_wp: --zellij-floating cannot be combined with --zellij-new-tab."
        in result.stderr
    )
    assert _read_fake_zellij_calls(capture_path) == []


def test_codex_wp_zellij_floating_uses_configured_defaults_from_env(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
            ENV_CODEX_WP_ZELLIJ_FLOAT_TOP: "9%",
            ENV_CODEX_WP_ZELLIJ_FLOAT_RIGHT: "4%",
            ENV_CODEX_WP_ZELLIJ_FLOAT_WIDTH: "50%",
            ENV_CODEX_WP_ZELLIJ_FLOAT_HEIGHT: "30%",
            ENV_CODEX_WP_ZELLIJ_FLOAT_CLOSE_ON_EXIT: "true",
            ENV_CODEX_WP_ZELLIJ_FLOAT_NAME: "config-pane",
            ENV_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX: "cdx:",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-dry-run",
            "exec",
            "--json",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "floating=top=9% right=4% width=50% height=30% close_on_exit=true",
        (
            "command=zellij run --floating --close-on-exit --pinned true --cwd "
            "/home/pets/TOOLS/cdx_proxy_cli_v2 --name cdx:\\ config-pane --x 64 --y 4 --width 70 "
            "--height 13 -- /home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec --json "
            "Reply\\ with\\ exactly\\ REQ1\\ OK\\ and\\ stop."
        ),
    ]
    assert _read_fake_zellij_calls(capture_path) == [
        ["action", "list-tabs", "--json", "--state", "--dimensions"]
    ]


def test_codex_wp_zellij_floating_uses_fallback_title_when_auto_name_is_disabled(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
            ENV_CODEX_WP_ZELLIJ_AUTO_NAME: "false",
            ENV_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX: "cdx:",
            ENV_CODEX_WP_ZELLIJ_TITLE_FALLBACK: "Codex Pilot",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-dry-run",
            "exec",
            "--json",
            "Summarize proxy retry jitter.",
        ],
        env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "floating=top=12% right=2% width=40% height=35% close_on_exit=false",
        (
            "command=zellij run --floating --pinned true --cwd /home/pets/TOOLS/cdx_proxy_cli_v2 "
            "--name cdx:\\ Codex\\ Pilot --x 81 --y 5 --width 56 --height 15 -- "
            "/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec --json "
            "Summarize\\ proxy\\ retry\\ jitter."
        ),
    ]


def test_codex_wp_zellij_floating_does_not_duplicate_title_prefix(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
            ENV_CODEX_WP_ZELLIJ_FLOAT_NAME: "cdx: Explicit Pane",
            ENV_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX: "cdx:",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-dry-run",
            "exec",
            "--json",
            "Reply with exactly REQ1 OK and stop.",
        ],
        env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "floating=top=12% right=2% width=40% height=35% close_on_exit=false",
        (
            "command=zellij run --floating --pinned true --cwd /home/pets/TOOLS/cdx_proxy_cli_v2 "
            "--name cdx:\\ Explicit\\ Pane --x 81 --y 5 --width 56 --height 15 -- "
            "/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec --json "
            "Reply\\ with\\ exactly\\ REQ1\\ OK\\ and\\ stop."
        ),
    ]


def test_codex_wp_zellij_floating_math_prompt_maps_to_semantic_title(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating",
            "--zellij-dry-run",
            "exec",
            "1+2=...",
        ],
        env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "floating=top=12% right=2% width=40% height=35% close_on_exit=false",
        (
            "command=zellij run --floating --pinned true --cwd /home/pets/TOOLS/cdx_proxy_cli_v2 "
            "--name cdx:\\ Math\\ Check --x 81 --y 5 --width 56 --height 15 -- "
            "/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec 1+2=..."
        ),
    ]


def test_codex_wp_zellij_new_tab_uses_prompt_derived_name_by_default(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": "[]",
            ENV_CODEX_WP_ZELLIJ_TITLE_MAX_WORDS: "2",
            ENV_CODEX_WP_ZELLIJ_TITLE_CASE: "title",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-new-tab",
            "--zellij-dry-run",
            "exec",
            "--json",
            "Proxy retry jitter diagnostics.",
        ],
        env,
    )

    expected_layout = ROOT / "layouts/zellij/three-vertical.kdl"
    expected_command = (
        f"command=zellij action new-tab --name Proxy\\ Retry --cwd {ROOT} "
        f"--layout {expected_layout} -- {ROOT / 'bin/codex_wp'} exec --json "
        "Proxy\\ retry\\ jitter\\ diagnostics."
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f"layout={expected_layout}", expected_command]
    assert _read_fake_zellij_calls(capture_path) == [["action", "list-tabs", "--json"]]


def test_codex_wp_zellij_pair_requires_explicit_shared_args_delimiter(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(tmp_path, capture_path)

    result = _run_codex_wp_args(
        [
            "--zellij-floating-pair",
            "--a-prompt",
            "Reply with exactly REQ1 OK and stop.",
            "--b-prompt",
            "1+2=...",
            "--json",
        ],
        env,
    )

    assert result.returncode == 2
    assert (
        "pair mode requires shared inner args after an explicit '--' delimiter."
        in result.stderr
    )
    assert _read_fake_zellij_calls(capture_path) == []


def test_codex_wp_zellij_pair_dry_run_prints_two_semantic_commands(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating-pair",
            "--zellij-dry-run",
            "--a-prompt",
            "Reply with exactly REQ1 OK and stop.",
            "--b-prompt",
            "1+2=...",
        ],
        env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "mode=zellij-floating-pair layout=top-right-double",
        'pane[a]=none title="cdx: REQ1 Check" state=planned',
        (
            "pane[a].command=zellij run --floating --pinned true --cwd /home/pets/TOOLS/cdx_proxy_cli_v2 "
            "--name cdx:\\ REQ1\\ Check --x 81 --y 5 --width 56 --height 14 -- "
            "/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec Reply\\ with\\ exactly\\ REQ1\\ OK\\ and\\ stop."
        ),
        'pane[b]=none title="cdx: Math Check" state=planned',
        (
            "pane[b].command=zellij run --floating --pinned true --cwd /home/pets/TOOLS/cdx_proxy_cli_v2 "
            "--name cdx:\\ Math\\ Check --x 81 --y 20 --width 56 --height 15 -- "
            "/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp exec 1+2=..."
        ),
    ]


def test_codex_wp_zellij_pair_launches_two_panes_and_renames_by_id(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
            "FAKE_ZELLIJ_RUN_STDOUT_1": "terminal_21",
            "FAKE_ZELLIJ_RUN_STDOUT_2": "terminal_22",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating-pair",
            "--a-prompt",
            "Reply with exactly REQ1 OK and stop.",
            "--b-prompt",
            "1+2=...",
        ],
        env,
    )

    list_tabs_call, run_a, run_b, rename_a, rename_b = _extract_pair_run_payloads(
        capture_path
    )

    assert result.returncode == 0, result.stderr
    assert "--state" in list_tabs_call
    assert "--dimensions" in list_tabs_call
    assert run_a[:17] == [
        "run",
        "--floating",
        "--pinned",
        "true",
        "--cwd",
        str(ROOT),
        "--name",
        "cdx:a",
        "--x",
        "81",
        "--y",
        "5",
        "--width",
        "56",
        "--height",
        "14",
        "--",
    ]
    assert run_b[:17] == [
        "run",
        "--floating",
        "--pinned",
        "true",
        "--cwd",
        str(ROOT),
        "--name",
        "cdx:b",
        "--x",
        "81",
        "--y",
        "20",
        "--width",
        "56",
        "--height",
        "15",
        "--",
    ]
    assert rename_a == [
        "action",
        "rename-pane",
        "--pane-id",
        "terminal_21",
        "cdx: REQ1 Check",
    ]
    assert rename_b == [
        "action",
        "rename-pane",
        "--pane-id",
        "terminal_22",
        "cdx: Math Check",
    ]
    assert result.stdout.splitlines() == [
        "mode=zellij-floating-pair layout=top-right-double",
        'pane[a]=terminal_21 title="cdx: REQ1 Check" state=renamed',
        'pane[b]=terminal_22 title="cdx: Math Check" state=renamed',
    ]


def test_codex_wp_zellij_pair_reads_prompt_files_for_each_pane(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"
    prompt_a = tmp_path / "prompt-a.md"
    prompt_b = tmp_path / "prompt-b.md"
    prompt_a.write_text("Reply with exactly REQ1 OK and stop.\n", encoding="utf-8")
    prompt_b.write_text("1+2=...\n", encoding="utf-8")

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
            "FAKE_ZELLIJ_RUN_STDOUT_1": "terminal_31",
            "FAKE_ZELLIJ_RUN_STDOUT_2": "terminal_32",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating-pair",
            "--a-file",
            str(prompt_a),
            "--b-file",
            str(prompt_b),
            "--",
            "--json",
        ],
        env,
    )

    _list_tabs_call, run_a, run_b, _rename_a, _rename_b = _extract_pair_run_payloads(
        capture_path
    )
    separator_a = run_a.index("--")
    separator_b = run_b.index("--")

    assert result.returncode == 0, result.stderr
    assert run_a[separator_a + 1 :] == [
        str(ROOT / "bin/codex_wp"),
        "exec",
        "--json",
        "Reply with exactly REQ1 OK and stop.\n",
    ]
    assert run_b[separator_b + 1 :] == [
        str(ROOT / "bin/codex_wp"),
        "exec",
        "--json",
        "1+2=...\n",
    ]


def test_codex_wp_zellij_pair_returns_partial_failure_when_second_pane_fails(
    tmp_path: Path,
) -> None:
    _write_fake_zellij(tmp_path)
    capture_path = tmp_path / "fake_zellij.jsonl"

    env = _zellij_env(
        tmp_path,
        capture_path,
        extra_env={
            "FAKE_ZELLIJ_LIST_TABS_STDOUT": json.dumps(
                [
                    {
                        "name": "Tab #1",
                        "active": True,
                        "viewport_columns": 140,
                        "viewport_rows": 42,
                    }
                ]
            ),
            "FAKE_ZELLIJ_RUN_STDOUT_1": "terminal_41",
            "FAKE_ZELLIJ_RUN_EXIT_2": "1",
        },
    )

    result = _run_codex_wp_args(
        [
            "--zellij-floating-pair",
            "--a-prompt",
            "Reply with exactly REQ1 OK and stop.",
            "--b-prompt",
            "1+2=...",
        ],
        env,
    )

    calls = _read_fake_zellij_calls(capture_path)
    rename_calls = [call for call in calls if call[:2] == ["action", "rename-pane"]]

    assert result.returncode == 3
    assert rename_calls == [
        ["action", "rename-pane", "--pane-id", "terminal_41", "cdx: REQ1 Check"]
    ]
    assert result.stdout.splitlines() == [
        "mode=zellij-floating-pair layout=top-right-double",
        'pane[a]=terminal_41 title="cdx: REQ1 Check" state=renamed',
        'pane[b]=none title="cdx: Math Check" state=failed',
    ]


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
        before_status = run_cli(
            "status", "--json", "--auth-dir", str(auth_dir), env=env
        )
        _assert_ok(before_status, label="cdx status before")
        before_status_payload = json.loads(before_status.stdout)
        assert before_status_payload["healthy"] is True

        before_doctor = run_cli(
            "doctor", "--json", "--auth-dir", str(auth_dir), env=env
        )
        _assert_ok(before_doctor, label="cdx doctor before")
        before_doctor_payload = json.loads(before_doctor.stdout)
        assert before_doctor_payload["summary"]["blacklist"] == 0

        requests_before = int(
            _debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"][
                "requests_total"
            ]
        )
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
                _debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"][
                    "requests_total"
                ]
            )

            result = _run_codex_wp(prompt, wrapper_env)
            assert result.returncode == 0, result.stderr or result.stdout

            stream = _parse_json_stream(result.stdout)
            _assert_json_stream_shape(stream)
            assert _final_message(stream) == expected

            step_requests_after = int(
                _debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"][
                    "requests_total"
                ]
            )
            assert step_requests_after - step_requests_before == 1

            delta_events = _jsonl_slice(events_file, step_events_before)
            proxy_events = [
                event for event in delta_events if event.get("event") == "proxy.request"
            ]
            assert proxy_events, f"missing proxy.request for request {index}"
            assert any(
                str(event.get("path") or "").endswith("/responses")
                for event in proxy_events
            )
            assert any(int(event.get("status", 0)) == 200 for event in proxy_events)

            for event in proxy_events:
                request_id = str(event.get("request_id") or "")
                assert request_id
                seen_request_ids.append(request_id)
                assert int(event.get("attempt", 0)) == 1

        requests_after = int(
            _debug_payload(base_url, env["CLIPROXY_MANAGEMENT_KEY"])["metrics"][
                "requests_total"
            ]
        )
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
