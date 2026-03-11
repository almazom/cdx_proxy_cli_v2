from __future__ import annotations

import json
from pathlib import Path

from tests.integration.support import (
    DEFAULT_TEST_INPUT,
    DEFAULT_TEST_MODEL,
    LOOPBACK_HOST,
    RESPONSES_PATH,
    TRACE_PATH,
    MockUpstreamHandler,
    make_usage_payload,
    parse_shell_exports,
    read_management_key,
    request_json,
    run_cli,
    write_auth,
)


def _assert_ok(result, *, label: str) -> None:
    assert result.returncode == 0, f"{label} failed: {result.stderr or result.stdout}"


def _cli_env(auth_dir: Path, upstream_base_url: str) -> dict[str, str]:
    return {
        "CLIPROXY_AUTH_DIR": str(auth_dir),
        "CLIPROXY_USAGE_BASE_URL": upstream_base_url,
        "CLIPROXY_MANAGEMENT_KEY": read_management_key(auth_dir),
    }


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
    base_url = exports["OPENAI_BASE_URL"]
    assert exports["OPENAI_API_BASE"] == base_url
    return base_url


def _stop_proxy(auth_dir: Path, env: dict[str, str]) -> None:
    stop = run_cli("stop", "--auth-dir", str(auth_dir), env=env)
    _assert_ok(stop, label="cdx stop")


def test_cli_runtime_flow_covers_status_doctor_all_reset_and_trace(
    tmp_path: Path,
    upstream_server: str,
) -> None:
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()
    write_auth(auth_dir / "a.json", "tok-a", "a@example.com", "acc-a")
    write_auth(auth_dir / "b.json", "tok-b", "b@example.com", "acc-b")

    MockUpstreamHandler.reset()
    MockUpstreamHandler.set_usage_payload(
        "tok-a",
        make_usage_payload(
            five_hour_used_percent=25,
            weekly_used_percent=100,
            weekly_reset_after_seconds=4 * 60 * 60,
            limit_reached=True,
        ),
    )
    MockUpstreamHandler.set_usage_payload(
        "tok-b",
        make_usage_payload(
            five_hour_used_percent=10,
            weekly_used_percent=15,
            weekly_reset_after_seconds=2 * 60 * 60,
        ),
    )

    base_url = _start_proxy(auth_dir, upstream_server)
    env = _cli_env(auth_dir, upstream_server)

    try:
        status = run_cli("status", "--json", "--auth-dir", str(auth_dir), env=env)
        _assert_ok(status, label="cdx status")
        status_payload = json.loads(status.stdout)
        assert status_payload["healthy"] is True
        assert status_payload["pid_running"] is True
        assert status_payload["base_url"] == base_url

        doctor = run_cli("doctor", "--json", "--auth-dir", str(auth_dir), env=env)
        _assert_ok(doctor, label="cdx doctor")
        doctor_payload = json.loads(doctor.stdout)
        assert doctor_payload["summary"]["cooldown"] == 1
        assert doctor_payload["summary"]["whitelist"] == 1
        cooldown_account = next(
            item for item in doctor_payload["accounts"] if item["file"] == "a.json"
        )
        assert cooldown_account["status"] == "COOLDOWN"
        assert cooldown_account["reason"] == "limit_weekly"

        all_result = run_cli("all", "--json", "--auth-dir", str(auth_dir), env=env)
        _assert_ok(all_result, label="cdx all")
        all_payload = json.loads(all_result.stdout)
        assert all_payload["aggregate"]["counts"]["cooldown"] == 1
        assert all_payload["availability"]["available_now"] == 1
        assert any(
            item["file"] == "a.json" and item["status"] == "COOLDOWN"
            for item in all_payload["accounts"]
        )

        response_status, response_body = request_json(
            base_url=base_url,
            path=RESPONSES_PATH,
            method="POST",
            payload={"model": DEFAULT_TEST_MODEL, "input": DEFAULT_TEST_INPUT},
        )
        assert response_status == 200
        assert response_body["status"] == "completed"

        trace_status, trace_body = request_json(
            base_url=base_url,
            path=f"{TRACE_PATH}?limit=10",
            headers={"X-Management-Key": env["CLIPROXY_MANAGEMENT_KEY"]},
        )
        assert trace_status == 200
        assert any(event["event"] == "proxy.request" for event in trace_body["events"])

        reset = run_cli(
            "reset",
            "--json",
            "--auth-dir",
            str(auth_dir),
            "--state",
            "cooldown",
            env=env,
        )
        _assert_ok(reset, label="cdx reset")
        reset_payload = json.loads(reset.stdout)
        assert reset_payload["reset"] == 0

        doctor_after_reset = run_cli(
            "doctor",
            "--json",
            "--auth-dir",
            str(auth_dir),
            env=env,
        )
        _assert_ok(doctor_after_reset, label="cdx doctor after reset")
        doctor_after_payload = json.loads(doctor_after_reset.stdout)
        cooldown_after = next(
            item for item in doctor_after_payload["accounts"] if item["file"] == "a.json"
        )
        assert cooldown_after["status"] == "COOLDOWN"
        assert cooldown_after["reason"] == "limit_weekly"
    finally:
        _stop_proxy(auth_dir, env)
