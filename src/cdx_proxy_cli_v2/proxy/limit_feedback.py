from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, Optional, Tuple

from cdx_proxy_cli_v2.auth.eligibility import (
    DEFAULT_LIMIT_COOLDOWN_AT,
    DEFAULT_LIMIT_WARN_AT,
)
from cdx_proxy_cli_v2.health_snapshot import window_summary
from cdx_proxy_cli_v2.limits_domain import (
    FIVE_HOURS_SECONDS,
    WEEK_SECONDS,
    extract_limits,
    overall_status,
)

FIVE_HOUR_WINDOW_MINUTES = FIVE_HOURS_SECONDS // 60
WEEK_WINDOW_MINUTES = WEEK_SECONDS // 60

WINDOW_KEY_BY_MINUTES = {
    FIVE_HOUR_WINDOW_MINUTES: "five_hour",
    WEEK_WINDOW_MINUTES: "weekly",
}

HEADER_WINDOW_SPECS = {
    "primary": {
        "used_percent": "x-codex-primary-used-percent",
        "window_minutes": "x-codex-primary-window-minutes",
        "reset_at": "x-codex-primary-reset-at",
        "fallback_window_minutes": FIVE_HOUR_WINDOW_MINUTES,
    },
    "secondary": {
        "used_percent": "x-codex-secondary-used-percent",
        "window_minutes": "x-codex-secondary-window-minutes",
        "reset_at": "x-codex-secondary-reset-at",
        "fallback_window_minutes": WEEK_WINDOW_MINUTES,
    },
}


def _parse_float(raw: object) -> Optional[float]:
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(raw: object) -> Optional[int]:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _reset_after_seconds(*, reset_at: Optional[int], now: float) -> Optional[int]:
    if reset_at is None or reset_at <= 0:
        return None
    return max(0, int(reset_at - now))


def _header_map(headers: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, value in headers:
        result[str(key).lower()] = str(value)
    return result


def _window_from_rate_limit_snapshot(
    snapshot: Optional[Dict[str, Any]],
    *,
    fallback_window_minutes: Optional[int] = None,
    now: float,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not isinstance(snapshot, dict):
        return None
    used_percent = _parse_float(snapshot.get("used_percent"))
    if used_percent is None:
        return None
    window_minutes = _parse_int(snapshot.get("window_minutes"))
    if window_minutes is None:
        limit_window_seconds = _parse_int(snapshot.get("limit_window_seconds"))
        if limit_window_seconds is not None:
            window_minutes = limit_window_seconds // 60
    if window_minutes is None:
        window_minutes = fallback_window_minutes
    if window_minutes not in WINDOW_KEY_BY_MINUTES:
        return None
    reset_after = _parse_int(snapshot.get("reset_after_seconds"))
    if reset_after is None:
        reset_after = _reset_after_seconds(
            reset_at=_parse_int(snapshot.get("resets_at"))
            or _parse_int(snapshot.get("reset_at")),
            now=now,
        )
    window_key = WINDOW_KEY_BY_MINUTES[window_minutes]
    summary = window_summary(
        {
            "used_percent": used_percent,
            "reset_after_seconds": reset_after,
        },
        limit_reached=bool(snapshot.get("limit_reached")),
        warn_at=DEFAULT_LIMIT_WARN_AT,
        cooldown_at=DEFAULT_LIMIT_COOLDOWN_AT,
    )
    if summary is None:
        return None
    return window_key, summary


def _windows_from_headers(
    headers: Iterable[Tuple[str, str]], *, now: float
) -> Dict[str, Dict[str, Any]]:
    header_values = _header_map(headers)
    windows: Dict[str, Dict[str, Any]] = {}
    for spec in HEADER_WINDOW_SPECS.values():
        snapshot = {
            "used_percent": header_values.get(spec["used_percent"]),
            "window_minutes": header_values.get(spec["window_minutes"]),
            "resets_at": header_values.get(spec["reset_at"]),
        }
        parsed = _window_from_rate_limit_snapshot(
            snapshot,
            fallback_window_minutes=int(spec["fallback_window_minutes"]),
            now=now,
        )
        if parsed is None:
            continue
        window_key, summary = parsed
        windows[window_key] = summary
    return windows


def _windows_from_body(body: bytes, *, now: float) -> Dict[str, Dict[str, Any]]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    windows: Dict[str, Dict[str, Any]] = {}

    rate_limits = payload.get("rate_limits")
    if isinstance(rate_limits, dict):
        for key in ("primary", "secondary"):
            parsed = _window_from_rate_limit_snapshot(
                rate_limits.get(key),
                fallback_window_minutes=(
                    FIVE_HOUR_WINDOW_MINUTES if key == "primary" else WEEK_WINDOW_MINUTES
                ),
                now=now,
            )
            if parsed is None:
                continue
            window_key, summary = parsed
            windows[window_key] = summary

    rate_limit = payload.get("rate_limit")
    if isinstance(rate_limit, dict):
        limit_reached = bool(rate_limit.get("limit_reached"))
        extracted = extract_limits(rate_limit)
        for window_key in ("five_hour", "weekly"):
            raw_window = extracted.get(window_key)
            summary = window_summary(
                raw_window if isinstance(raw_window, dict) else None,
                limit_reached=limit_reached,
                warn_at=DEFAULT_LIMIT_WARN_AT,
                cooldown_at=DEFAULT_LIMIT_COOLDOWN_AT,
            )
            if summary is not None:
                windows[window_key] = summary

    return windows


def parse_limit_feedback(
    *, headers: Iterable[Tuple[str, str]], body: bytes
) -> Optional[Dict[str, Any]]:
    now = time.time()
    windows = _windows_from_headers(headers, now=now)
    body_windows = _windows_from_body(body, now=now)
    for window_key, summary in body_windows.items():
        windows.setdefault(window_key, summary)

    if not windows:
        return None

    statuses = [
        str(window.get("status") or "UNKNOWN")
        for window in windows.values()
        if isinstance(window, dict)
    ]
    payload: Dict[str, Any] = {
        "status": overall_status(statuses) if statuses else "UNKNOWN",
        "error": None,
    }
    for window_key in ("five_hour", "weekly"):
        if window_key in windows:
            payload[window_key] = windows[window_key]
    return payload


def merge_limit_feedback(
    *,
    existing: Optional[Dict[str, Any]],
    feedback: Dict[str, Any],
    auth_name: str,
    auth_email: Optional[str],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(existing or {})
    for key in ("five_hour", "weekly"):
        if isinstance(feedback.get(key), dict):
            merged[key] = dict(feedback[key])

    statuses = [
        str(window.get("status") or "UNKNOWN")
        for window in (merged.get("five_hour"), merged.get("weekly"))
        if isinstance(window, dict)
    ]
    merged["file"] = auth_name
    merged["email"] = auth_email
    merged["status"] = overall_status(statuses) if statuses else "UNKNOWN"
    merged["error"] = None
    return merged
