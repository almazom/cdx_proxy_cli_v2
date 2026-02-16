from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Dict, List, Optional

FIVE_HOURS_SECONDS = 5 * 60 * 60
WEEK_SECONDS = 7 * 24 * 60 * 60


def normalize_base_url(url: str) -> str:
    normalized = (url or "").strip()
    while normalized.endswith("/"):
        normalized = normalized[:-1]
    if (
        (normalized.startswith("https://chatgpt.com") or normalized.startswith("https://chat.openai.com"))
        and "/backend-api" not in normalized
    ):
        normalized = f"{normalized}/backend-api"
    return normalized


def usage_url(base_url: str) -> str:
    base = normalize_base_url(base_url)
    if "/backend-api" in base:
        return f"{base}/wham/usage"
    return f"{base}/api/codex/usage"


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, binascii.Error):
        return {}


def extract_limits(rate_limit: Optional[Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    limits: Dict[str, Optional[Dict[str, Any]]] = {"five_hour": None, "weekly": None}
    if not isinstance(rate_limit, dict):
        return limits
    windows = [rate_limit.get("primary_window"), rate_limit.get("secondary_window")]
    for window in windows:
        if not isinstance(window, dict):
            continue
        seconds = window.get("limit_window_seconds")
        if seconds == FIVE_HOURS_SECONDS and limits["five_hour"] is None:
            limits["five_hour"] = window
        elif seconds == WEEK_SECONDS and limits["weekly"] is None:
            limits["weekly"] = window
    return limits


def classify_status(
    used_percent: Optional[float],
    limit_reached: bool,
    warn_at: int,
    cooldown_at: int,
) -> str:
    if limit_reached:
        return "COOLDOWN"
    if used_percent is None:
        return "UNKNOWN"
    if used_percent >= cooldown_at:
        return "COOLDOWN"
    if used_percent >= warn_at:
        return "WARN"
    return "OK"


def overall_status(statuses: List[str]) -> str:
    if any(status == "COOLDOWN" for status in statuses):
        return "COOLDOWN"
    if any(status == "WARN" for status in statuses):
        return "WARN"
    if any(status == "OK" for status in statuses):
        return "OK"
    return "UNKNOWN"
