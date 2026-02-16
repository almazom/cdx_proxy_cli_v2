from __future__ import annotations

import ipaddress
from typing import Dict, Optional
from urllib.parse import urlsplit

CHATGPT_HOSTS = {"chatgpt.com", "chat.openai.com"}

CHATGPT_RESPONSES_DROP_HEADERS = {
    "originator",
    "version",
    "x-codex-beta-features",
    "x-oai-web-search-eligible",
    "x-codex-turn-metadata",
    "session_id",
    "chatgpt-account-id",
}

PATH_REWRITE_PATTERNS = [
    ("/v1/responses/compact", "/codex/responses/compact"),
    ("/responses/compact", "/codex/responses/compact"),
    ("/v1/responses", "/codex/responses"),
    ("/responses", "/codex/responses"),
]


def is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if not normalized:
        return False
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def trace_route(path: str) -> str:
    path_only = (path or "").split("?", 1)[0]
    if path_only.endswith("/compact"):
        return "compact"
    if "/responses" in path_only:
        return "request"
    return "other"


def management_route(path: str) -> Optional[str]:
    path_only = urlsplit(path or "").path
    if path_only == "/debug":
        return "debug"
    if path_only == "/trace":
        return "trace"
    if path_only == "/health":
        return "health"
    if path_only == "/auth-files":
        return "auth-files"
    if path_only == "/shutdown":
        return "shutdown"
    return None


def rewrite_request_path(*, req_path: str, upstream_host: Optional[str], upstream_base_path: str) -> str:
    host = (upstream_host or "").lower()
    if host not in CHATGPT_HOSTS:
        return req_path
    if upstream_base_path.rstrip("/") != "/backend-api":
        return req_path
    for old_prefix, new_prefix in PATH_REWRITE_PATTERNS:
        if req_path.startswith(old_prefix):
            suffix = req_path[len(old_prefix) :]
            return f"{new_prefix}{suffix}"
    return req_path


def is_primary_responses_path(req_path: str) -> bool:
    return req_path.split("?", 1)[0] == "/codex/responses"


def drop_header_case_insensitive(headers: Dict[str, str], key: str) -> None:
    for existing in list(headers.keys()):
        if existing.lower() == key.lower():
            headers.pop(existing, None)
            return


def set_header_case_insensitive(headers: Dict[str, str], key: str, value: str) -> None:
    drop_header_case_insensitive(headers, key)
    headers[key] = value


def build_forward_headers(incoming_headers: Dict[str, str], *, chatgpt_responses_mode: bool) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    allowed_chatgpt_headers = {"accept", "content-type", "content-encoding", "user-agent"}
    for key, value in incoming_headers.items():
        normalized = key.lower()
        if normalized in {"host", "content-length", "connection", "transfer-encoding"}:
            continue
        if chatgpt_responses_mode and (normalized in CHATGPT_RESPONSES_DROP_HEADERS or "_" in key):
            continue
        if chatgpt_responses_mode:
            if normalized in allowed_chatgpt_headers or normalized.startswith("x-openai-") or normalized.startswith("openai-"):
                headers[key] = value
            continue
        headers[key] = value
    return headers
