from __future__ import annotations

from cdx_proxy_cli_v2.proxy.rules import rewrite_request_path, trace_route


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
