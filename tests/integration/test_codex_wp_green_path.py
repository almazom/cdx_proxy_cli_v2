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
    ENV_CODEX_WP_ZELLIJ_PAIR_GAP,
    ENV_CODEX_WP_ZELLIJ_PAIR_HEIGHT,
    ENV_CODEX_WP_ZELLIJ_PAIR_LAYOUT,
    ENV_CODEX_WP_ZELLIJ_PAIR_RIGHT,
    ENV_CODEX_WP_ZELLIJ_PAIR_TOP,
    ENV_CODEX_WP_ZELLIJ_PAIR_WIDTH,
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


def _write_fake_zellij(tmp_path: Path) -> tuple[Path, Path]:
    capture_path = tmp_path / "fake_zellij.jsonl"
    body = f"""#!{sys.executable}
from __future__ import annotations

import json
import os
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
    sys.stdout.write(
        os.environ.get(f"FAKE_ZELLIJ_RUN_STDOUT_{{suffix}}")
        or os.environ.get("FAKE_ZELLIJ_RUN_STDOUT", "terminal_11")
    )
    sys.stderr.write(
        os.environ.get(f"FAKE_ZELLIJ_RUN_STDERR_{{suffix}}")
        or os.environ.get("FAKE_ZELLIJ_RUN_STDERR", "")
    )
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


def _extract_pair_run_payloads(path: Path) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    calls = _read_fake_zellij_calls(path)
    assert calls[0][:2] == ["action", "list-tabs"]
    assert "--json" in calls[0]
    run_calls = [call for call in calls if call[:1] == ["run"]]
    rename_calls = [call for call in calls if call[:2] == ["action", "rename-pane"]]
    assert len(run_calls) == 2
    assert len(rename_calls) == 2
    return calls[0], run_calls[0], run_calls[1], rename_calls[0], rename_calls[1]


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
        "Valid templates: single, three-horizontal, three-vertical."
        in result.stderr
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
    assert "codex_wp: --zellij-new-tab is required when using zellij mode." in result.stderr
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
    assert "codex_wp: --zellij-floating cannot be combined with --zellij-new-tab." in result.stderr
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
    assert "pair mode requires shared inner args after an explicit '--' delimiter." in result.stderr
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

    list_tabs_call, run_a, run_b, rename_a, rename_b = _extract_pair_run_payloads(capture_path)

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

    _list_tabs_call, run_a, run_b, _rename_a, _rename_b = _extract_pair_run_payloads(capture_path)
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
