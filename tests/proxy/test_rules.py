from __future__ import annotations

from cdx_proxy_cli_v2.proxy.rules import (
    get_request_timeout,
    management_route,
    rewrite_request_path,
    trace_route,
)


def test_rewrite_chatgpt_responses_paths() -> None:
    assert rewrite_request_path(
        req_path="/responses",
        upstream_host="chatgpt.com",
        upstream_base_path="/backend-api",
    ) == "/codex/responses"
    assert rewrite_request_path(
        req_path="/v1/responses/compact",
        upstream_host="chat.openai.com",
        upstream_base_path="/backend-api",
    ) == "/codex/responses/compact"


def test_no_rewrite_for_other_upstreams() -> None:
    assert rewrite_request_path(
        req_path="/responses",
        upstream_host="api.openai.com",
        upstream_base_path="/v1",
    ) == "/responses"


def test_trace_route_labels() -> None:
    assert trace_route("/responses") == "request"
    assert trace_route("/responses/compact?x=1") == "compact"
    assert trace_route("/health") == "other"


def test_get_request_timeout_for_compact() -> None:
    """Compact endpoints get longer timeout (120s) due to long-running conversation compression."""
    assert get_request_timeout("/responses/compact") == 120
    assert get_request_timeout("/v1/responses/compact") == 120
    assert get_request_timeout("/codex/responses/compact") == 120
    assert get_request_timeout("/responses/compact?previous_response_id=xyz") == 120


def test_get_request_timeout_for_regular_requests() -> None:
    """Regular endpoints use default timeout (25s)."""
    assert get_request_timeout("/responses") == 25
    assert get_request_timeout("/v1/responses") == 25
    assert get_request_timeout("/codex/responses") == 25
    assert get_request_timeout("/health") == 25
    assert get_request_timeout("/") == 25


def test_management_route_lookup() -> None:
    assert management_route("/debug") == "debug"
    assert management_route("/trace") == "trace"
    assert management_route("/health") == "health"
    assert management_route("/auth-files") == "auth-files"
    assert management_route("/shutdown") == "shutdown"
    assert management_route("/reset") == "reset"


def test_management_route_ignores_query_and_unknown() -> None:
    assert management_route("/debug?x=1") == "debug"
    assert management_route("/unknown") is None
