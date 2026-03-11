from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from cdx_proxy_cli_v2.health_snapshot import collective_health_snapshot

DEFAULT_LIMIT_WARN_AT = 70
DEFAULT_LIMIT_COOLDOWN_AT = 90
DEFAULT_LIMIT_TIMEOUT = 8
DEFAULT_USAGE_BASE_URL = "https://chatgpt.com/backend-api"
ELIGIBLE_ACCOUNT_STATUSES = {"OK", "WARN"}


def usage_base_url() -> str:
    return (
        str(os.environ.get("CLIPROXY_USAGE_BASE_URL") or DEFAULT_USAGE_BASE_URL).strip()
        or DEFAULT_USAGE_BASE_URL
    )


def fetch_limit_health(
    auth_dir: str,
    *,
    base_url: Optional[str] = None,
    warn_at: int = DEFAULT_LIMIT_WARN_AT,
    cooldown_at: int = DEFAULT_LIMIT_COOLDOWN_AT,
    timeout: int = DEFAULT_LIMIT_TIMEOUT,
) -> Dict[str, Dict[str, Any]]:
    snapshot = collective_health_snapshot(
        auths_dir=auth_dir,
        base_url=base_url or usage_base_url(),
        warn_at=warn_at,
        cooldown_at=cooldown_at,
        timeout=timeout,
        only="both",
    )
    accounts = snapshot.get("accounts", [])
    result: Dict[str, Dict[str, Any]] = {}
    if not isinstance(accounts, list):
        return result
    for account in accounts:
        if not isinstance(account, dict):
            continue
        auth_file = str(account.get("file") or "").strip()
        if not auth_file:
            continue
        result[auth_file] = account
    return result


def _window_reset_after_seconds(window: Optional[Dict[str, Any]]) -> Optional[int]:
    if not isinstance(window, dict):
        return None
    raw = window.get("reset_after_seconds")
    if isinstance(raw, (int, float)) and int(raw) > 0:
        return int(raw)
    return None


def _window_status(window: Optional[Dict[str, Any]]) -> str:
    if not isinstance(window, dict):
        return "UNKNOWN"
    return str(window.get("status") or "UNKNOWN").upper()


def limit_block_details(
    limit_health: Optional[Dict[str, Any]], *, now: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    if not isinstance(limit_health, dict):
        return None
    now_ts = float(now if now is not None else time.time())
    cooldown_windows: List[tuple[str, int]] = []
    for key in ("five_hour", "weekly"):
        window = limit_health.get(key)
        if _window_status(window) != "COOLDOWN":
            continue
        reset_after = _window_reset_after_seconds(window)
        if reset_after is None or reset_after <= 0:
            continue
        cooldown_windows.append((key, reset_after))
    if not cooldown_windows:
        return None
    reset_after_seconds = max(seconds for _key, seconds in cooldown_windows)
    keys = {key for key, _seconds in cooldown_windows}
    if keys == {"five_hour", "weekly"}:
        reason = "limit_weekly_and_5h"
    elif "weekly" in keys:
        reason = "limit_weekly"
    else:
        reason = "limit_5h"
    return {
        "reason": reason,
        "reason_origin": "limit",
        "cooldown_seconds": reset_after_seconds,
        "until": now_ts + reset_after_seconds,
    }


def merged_account_state(
    runtime_item: Dict[str, Any],
    limit_item: Dict[str, Any],
) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    item.update(limit_item)
    item.update(runtime_item)

    runtime_status = str(runtime_item.get("status") or "UNKNOWN").upper()
    runtime_eligible = bool(runtime_item.get("eligible_now", runtime_status == "OK"))
    runtime_reason = str(runtime_item.get("reason") or "").strip()
    runtime_origin = str(runtime_item.get("reason_origin") or "").strip()
    runtime_until = runtime_item.get("until")

    limit_block = limit_block_details(limit_item)
    limit_status = str(limit_item.get("status") or "UNKNOWN").upper()

    status = runtime_status
    if runtime_status in {"BLACKLIST", "PROBATION", "COOLDOWN"}:
        status = runtime_status
    elif limit_block:
        status = "COOLDOWN"
    elif limit_status == "WARN":
        status = "WARN"
    elif runtime_status == "UNKNOWN" and limit_status in ELIGIBLE_ACCOUNT_STATUSES:
        status = limit_status

    item["status"] = status
    item["eligible_now"] = bool(
        runtime_eligible and status in ELIGIBLE_ACCOUNT_STATUSES
    )

    if runtime_reason:
        item["reason"] = runtime_reason
        item["reason_origin"] = runtime_origin or "runtime"
    elif limit_block and status == "COOLDOWN":
        item["reason"] = limit_block["reason"]
        item["reason_origin"] = limit_block["reason_origin"]

    if limit_block and status == "COOLDOWN":
        item["until"] = max(
            float(runtime_until) if isinstance(runtime_until, (int, float)) else 0.0,
            float(limit_block["until"]),
        )
        runtime_cooldown = runtime_item.get("cooldown_seconds")
        item["cooldown_seconds"] = (
            max(
                int(runtime_cooldown)
                if isinstance(runtime_cooldown, (int, float))
                else 0,
                int(limit_block["cooldown_seconds"]),
            )
            or None
        )
    elif isinstance(runtime_until, (int, float)):
        item["until"] = float(runtime_until)

    return item


def merge_runtime_with_limits(
    runtime_accounts: List[Dict[str, Any]],
    limit_health_by_file: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    runtime_by_file: Dict[str, Dict[str, Any]] = {}
    for item in runtime_accounts:
        if not isinstance(item, dict):
            continue
        auth_file = str(item.get("file") or "").strip()
        if auth_file:
            runtime_by_file[auth_file] = item

    merged: List[Dict[str, Any]] = []
    for auth_file in sorted(
        set(runtime_by_file.keys()) | set(limit_health_by_file.keys())
    ):
        runtime_item = dict(runtime_by_file.get(auth_file, {}))
        limit_item = dict(limit_health_by_file.get(auth_file, {}))
        item = merged_account_state(runtime_item, limit_item)
        item["file"] = auth_file
        merged.append(item)
    return merged


def merged_ok(accounts: List[Dict[str, Any]]) -> bool:
    return any(
        bool(item.get("eligible_now")) for item in accounts if isinstance(item, dict)
    )
