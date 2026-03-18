from __future__ import annotations

import json
import threading
from typing import Any
from urllib.request import Request, urlopen

from tests.integration.support import (
    ACCOUNT_COMPATIBLE_FALLBACK_MODEL,
    ACCOUNT_INCOMPATIBLE_REQUEST_MODEL,
    CHAT_COMPLETIONS_PATH,
    DEBUG_PATH,
    DEFAULT_TEST_MODEL,
    HEALTH_PATH,
    MODELS_PATH,
    RESPONSES_PATH,
    TRACE_PATH,
    build_chat_completions_payload,
    build_responses_payload,
    MockUpstreamHandler,
    request_json,
)


def _upstream_path_count(path_prefix: str) -> int:
    return sum(
        1
        for path in MockUpstreamHandler.received_paths
        if path.split("?", 1)[0] == path_prefix
    )


def test_responses_request_succeeds(proxy_server: dict[str, Any]) -> None:
    status, body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=RESPONSES_PATH,
        method="POST",
        payload=build_responses_payload(),
    )

    assert status == 200
    assert body["id"] == "resp_123"
    assert body["status"] == "completed"


def test_models_are_normalized_for_codex(proxy_server: dict[str, Any]) -> None:
    status, body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=MODELS_PATH,
    )

    assert status == 200
    models = body["models"]
    assert models
    assert all(item["shell_type"] == "shell_command" for item in models)
    assert all(item["visibility"] == "list" for item in models)
    assert all(item["default_reasoning_level"] == "low" for item in models)


def test_streaming_responses_request_succeeds(proxy_server: dict[str, Any]) -> None:
    req = Request(
        f"{proxy_server['base_url']}{RESPONSES_PATH}",
        data=json.dumps(build_responses_payload(stream=True)).encode(),
        method="POST",
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
    )

    with urlopen(req, timeout=5.0) as response:
        assert response.status == 200
        assert response.headers.get("Content-Type") == "text/event-stream"
        assert b"data:" in response.read()


def test_rotates_after_401(proxy_server: dict[str, Any]) -> None:
    MockUpstreamHandler.responses = [
        {"status": 401, "data": {"error": {"code": "invalid_token"}}},
        {"status": 200, "data": {"id": "resp_retry", "status": "completed"}},
    ]

    status, body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=RESPONSES_PATH,
        method="POST",
        payload=build_responses_payload(model=DEFAULT_TEST_MODEL),
    )

    assert status == 200
    assert body["id"] == "resp_retry"
    assert _upstream_path_count(RESPONSES_PATH) == 2


def test_rotates_after_known_account_incompatible_400(
    proxy_server: dict[str, Any],
) -> None:
    MockUpstreamHandler.responses = [
        {
            "status": 400,
            "data": {
                "detail": f"The '{ACCOUNT_INCOMPATIBLE_REQUEST_MODEL}' model is not supported when using Codex with a ChatGPT account."
            },
        },
        {"status": 200, "data": {"id": "resp_retry_400", "status": "completed"}},
    ]

    status, body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=RESPONSES_PATH,
        method="POST",
        payload=build_responses_payload(model=ACCOUNT_COMPATIBLE_FALLBACK_MODEL),
    )

    assert status == 200
    assert body["id"] == "resp_retry_400"
    assert _upstream_path_count(RESPONSES_PATH) == 2


def test_returns_last_error_when_all_auths_fail(proxy_server: dict[str, Any]) -> None:
    MockUpstreamHandler.responses = [
        {"status": 401, "data": {"error": {"code": "invalid_token"}}},
        {"status": 401, "data": {"error": {"code": "invalid_token"}}},
    ]

    status, _body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=RESPONSES_PATH,
        method="POST",
        payload=build_responses_payload(model=DEFAULT_TEST_MODEL),
    )

    assert status == 401
    assert _upstream_path_count(RESPONSES_PATH) == 2


def test_management_endpoints_require_key(proxy_server: dict[str, Any]) -> None:
    status, body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=TRACE_PATH,
    )

    assert status == 401
    assert "unauthorized" in str(body.get("error", "")).lower()


def test_health_debug_and_trace_reflect_runtime(proxy_server: dict[str, Any]) -> None:
    management_headers = {
        "X-Management-Key": str(proxy_server["management_key"]),
    }

    request_json(
        base_url=str(proxy_server["base_url"]),
        path=RESPONSES_PATH,
        method="POST",
        payload=build_responses_payload(model=DEFAULT_TEST_MODEL),
    )

    health_status, health_body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=HEALTH_PATH,
        headers=management_headers,
    )
    debug_status, debug_body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=DEBUG_PATH,
        headers=management_headers,
    )
    trace_status, trace_body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=f"{TRACE_PATH}?limit=10",
        headers=management_headers,
    )

    assert health_status == 200
    assert health_body["ok"] is True
    assert len(health_body["accounts"]) == 2
    assert debug_status == 200
    assert debug_body["status"] == "running"
    assert debug_body["auth_count"] == 2
    assert trace_status == 200
    assert any(event["event"] == "proxy.request" for event in trace_body["events"])


def test_chat_completions_request_succeeds(proxy_server: dict[str, Any]) -> None:
    status, body = request_json(
        base_url=str(proxy_server["base_url"]),
        path=CHAT_COMPLETIONS_PATH,
        method="POST",
        payload=build_chat_completions_payload(),
    )

    assert status == 200
    assert "choices" in body


def test_concurrent_responses_requests_succeed(proxy_server: dict[str, Any]) -> None:
    results: list[tuple[int, dict[str, object]]] = []
    errors: list[Exception] = []

    def make_request() -> None:
        try:
            result = request_json(
                base_url=str(proxy_server["base_url"]),
                path=RESPONSES_PATH,
                method="POST",
                payload=build_responses_payload(model=DEFAULT_TEST_MODEL),
                timeout=10.0,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            return
        results.append(result)

    threads = [threading.Thread(target=make_request) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15.0)

    assert not errors
    assert len(results) == 5
    assert all(status == 200 for status, _body in results)


def test_forwarded_bearer_token_comes_from_auth_pool(
    proxy_server: dict[str, Any],
) -> None:
    MockUpstreamHandler.reset()

    request_json(
        base_url=str(proxy_server["base_url"]),
        path=RESPONSES_PATH,
        method="POST",
        payload=build_responses_payload(model=DEFAULT_TEST_MODEL),
    )

    assert MockUpstreamHandler.received_headers
    auth_header = MockUpstreamHandler.received_headers[0].get("Authorization", "")
    assert auth_header.startswith("Bearer ")
    assert auth_header.removeprefix("Bearer ") in {"tok-a", "tok-b"}
