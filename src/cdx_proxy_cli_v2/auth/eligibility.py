from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from cdx_proxy_cli_v2.health_snapshot import collective_health_snapshot

DEFAULT_LIMIT_WARN_AT = 70
DEFAULT_LIMIT_COOLDOWN_AT = 90
DEFAULT_LIMIT_TIMEOUT = 8
DEFAULT_LIMIT_RECHECK_SECONDS = 60
DEFAULT_LIMIT_MIN_REMAINING_PERCENT = 11.0
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
    min_remaining_percent: float = DEFAULT_LIMIT_MIN_REMAINING_PERCENT,
    timeout: int = DEFAULT_LIMIT_TIMEOUT,
    prefer_keyring: bool = True,
) -> Dict[str, Dict[str, Any]]:
    _ = float(min_remaining_percent)
    snapshot = collective_health_snapshot(
        auths_dir=auth_dir,
        base_url=base_url or usage_base_url(),
        warn_at=warn_at,
        cooldown_at=cooldown_at,
        timeout=timeout,
        only="both",
        prefer_keyring=prefer_keyring,
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


def _window_used_percent(window: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(window, dict):
        return None
    raw = window.get("used_percent")
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _window_is_preemptive_limit_cooldown(
    window: Optional[Dict[str, Any]], *, min_remaining_percent: float
) -> bool:
    used_percent = _window_used_percent(window)
    if used_percent is None:
        return False
    remaining_percent = 100.0 - used_percent
    return remaining_percent < max(0.0, float(min_remaining_percent))


def limit_block_details(
    limit_health: Optional[Dict[str, Any]],
    *,
    now: Optional[float] = None,
    min_remaining_percent: float = DEFAULT_LIMIT_MIN_REMAINING_PERCENT,
) -> Optional[Dict[str, Any]]:
    if not isinstance(limit_health, dict):
        return None
    now_ts = float(now if now is not None else time.time())
    cooldown_keys: List[str] = []
    guardrail_keys: List[str] = []
    cooldown_seconds: List[int] = []
    has_unknown_reset = False
    for key in ("five_hour", "weekly"):
        window = limit_health.get(key)
        window_status = _window_status(window)
        is_guardrail = _window_is_preemptive_limit_cooldown(
            window,
            min_remaining_percent=min_remaining_percent,
        )
        if window_status != "COOLDOWN" and not is_guardrail:
            continue
        if window_status == "COOLDOWN":
            cooldown_keys.append(key)
        else:
            guardrail_keys.append(key)
        reset_after = _window_reset_after_seconds(window)
        if reset_after is None or reset_after <= 0:
            has_unknown_reset = True
            continue
        cooldown_seconds.append(reset_after)
    effective_keys = cooldown_keys or guardrail_keys
    if not effective_keys:
        return None
    if has_unknown_reset:
        cooldown_seconds.append(DEFAULT_LIMIT_RECHECK_SECONDS)
    reset_after_seconds = max(cooldown_seconds)
    keys = set(effective_keys)
    if keys == {"five_hour", "weekly"}:
        reason = "limit_weekly_and_5h"
    elif "weekly" in keys:
        reason = "limit_weekly"
    else:
        reason = "limit_5h"
    reason_origin = "limit"
    if not cooldown_keys and guardrail_keys:
        reason = f"{reason}_guardrail"
        reason_origin = "limit_guardrail"
    return {
        "reason": reason,
        "reason_origin": reason_origin,
        "cooldown_seconds": reset_after_seconds,
        "until": now_ts + reset_after_seconds,
    }


def has_limit_window_data(limit_health: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(limit_health, dict):
        return False
    return any(
        isinstance(limit_health.get(key), dict) for key in ("five_hour", "weekly")
    )


def merged_account_state(
    runtime_item: Dict[str, Any],
    limit_item: Dict[str, Any],
    *,
    limit_snapshot_known: bool = True,
    min_remaining_percent: float = DEFAULT_LIMIT_MIN_REMAINING_PERCENT,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    item.update(limit_item)
    item.update(runtime_item)

    runtime_status = str(runtime_item.get("status") or "UNKNOWN").upper()
    runtime_eligible = bool(runtime_item.get("eligible_now", runtime_status == "OK"))
    runtime_reason = str(runtime_item.get("reason") or "").strip()
    runtime_origin = str(runtime_item.get("reason_origin") or "").strip()
    runtime_until = runtime_item.get("until")

    limit_has_data = has_limit_window_data(limit_item)
    limit_block = limit_block_details(
        limit_item,
        min_remaining_percent=min_remaining_percent,
    )
    limit_status = str(limit_item.get("status") or "UNKNOWN").upper()

    status = runtime_status
    if runtime_status in {"BLACKLIST", "PROBATION", "COOLDOWN"}:
        status = runtime_status
    elif runtime_status == "UNKNOWN":
        status = "COOLDOWN" if limit_block else "UNKNOWN"
    elif limit_snapshot_known and not limit_has_data:
        status = "UNKNOWN"
    elif limit_block:
        status = "COOLDOWN"
    elif limit_status == "WARN":
        status = "WARN"
    elif limit_snapshot_known and limit_status not in ELIGIBLE_ACCOUNT_STATUSES:
        status = "UNKNOWN"

    item["status"] = status
    item["eligible_now"] = bool(
        runtime_eligible
        and runtime_status in ELIGIBLE_ACCOUNT_STATUSES
        and (
            not limit_snapshot_known
            or (
                limit_has_data
                and limit_block is None
                and limit_status in ELIGIBLE_ACCOUNT_STATUSES
            )
        )
    )

    if runtime_reason:
        item["reason"] = runtime_reason
        item["reason_origin"] = runtime_origin or "runtime"
    elif limit_block and status == "COOLDOWN":
        item["reason"] = limit_block["reason"]
        item["reason_origin"] = limit_block["reason_origin"]
    elif runtime_status == "UNKNOWN":
        item["reason"] = "runtime_unavailable"
        item["reason_origin"] = "runtime"
    elif limit_snapshot_known and (
        not limit_has_data or limit_status not in ELIGIBLE_ACCOUNT_STATUSES
    ):
        item["reason"] = "limit_unavailable"
        item["reason_origin"] = "limit"

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
    *,
    limit_snapshot_known: bool = True,
    min_remaining_percent: float = DEFAULT_LIMIT_MIN_REMAINING_PERCENT,
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
        item = merged_account_state(
            runtime_item,
            limit_item,
            limit_snapshot_known=limit_snapshot_known,
            min_remaining_percent=min_remaining_percent,
        )
        item["file"] = auth_file
        merged.append(item)
    return merged


def merged_ok(accounts: List[Dict[str, Any]]) -> bool:
    return any(
        bool(item.get("eligible_now")) for item in accounts if isinstance(item, dict)
    )
