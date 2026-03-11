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

MANAGEMENT_ROUTES = {
    "/debug": "debug",
    "/trace": "trace",
    "/health": "health",
    "/auth-files": "auth-files",
    "/shutdown": "shutdown",
    "/reset": "reset",
    "/probe": "probe",
}


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
    path_only = urlsplit(path or "").path.rstrip("/")
    if management_route(path):
        return "management"
    if path_only.endswith("/compact"):
        return "compact"
    if path_only.endswith("/models"):
        return "models"
    if "/responses" in path_only:
        return "responses"
    return ""


def management_route(path: str) -> Optional[str]:
    path_only = urlsplit(path or "").path
    return MANAGEMENT_ROUTES.get(path_only)


def rewrite_request_path(
    *, req_path: str, upstream_host: Optional[str], upstream_base_path: str
) -> str:
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
    path = req_path.split("?", 1)[0]
    return path in {"/codex/responses", "/codex/responses/compact"}


def get_request_timeout(req_path: str, default: int = 25, compact: int = 120) -> int:
    """Return appropriate timeout based on endpoint type.

    /compact endpoints can take significantly longer as they process
    and compress large conversation histories. Research shows these
    operations can take 30-300+ seconds depending on conversation size.
    """
    path = req_path.split("?", 1)[0]
    if path.endswith("/compact"):
        return compact
    return default


def drop_header_case_insensitive(headers: Dict[str, str], key: str) -> None:
    target = key.lower()
    for existing in list(headers.keys()):
        if existing.lower() == target:
            headers.pop(existing, None)


def set_header_case_insensitive(headers: Dict[str, str], key: str, value: str) -> None:
    drop_header_case_insensitive(headers, key)
    headers[key] = value


def build_forward_headers(
    incoming_headers: Dict[str, str],
    *,
    chatgpt_backend: bool = False,
    chatgpt_responses_mode: bool = False,
    websocket_upgrade: bool = False,
) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    # Hop-by-hop headers that should not be forwarded
    hop_by_hop = {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
    }

    for key, value in incoming_headers.items():
        normalized = key.lower()
        # Skip hop-by-hop headers (except for WebSocket upgrade)
        if normalized in hop_by_hop:
            if websocket_upgrade and normalized in {"upgrade", "connection"}:
                headers[key] = value
            continue

        if chatgpt_responses_mode:
            # For ChatGPT mode: forward ALL headers transparently
            # except known problematic ones for responses endpoints
            if normalized in CHATGPT_RESPONSES_DROP_HEADERS:
                continue
            headers[key] = value
        else:
            # API mode: forward everything except hop-by-hop
            headers[key] = value

    if chatgpt_backend:
        # Enforce canonical headers for ChatGPT backend to avoid CSRF/Referer blocks
        set_header_case_insensitive(headers, "Origin", "https://chatgpt.com")
        set_header_case_insensitive(headers, "Referer", "https://chatgpt.com/")
        set_header_case_insensitive(headers, "User-Agent", "codex-cli")

    return headers
