from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cdx_proxy_cli_v2.auth.store import load_auth_records
from cdx_proxy_cli_v2.limits_domain import (
    classify_status,
    extract_limits,
    overall_status,
    usage_url,
)

DEFAULT_USER_AGENT = "codex-cli"
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def window_summary(
    window: Optional[Dict[str, Any]],
    *,
    limit_reached: bool,
    warn_at: int,
    cooldown_at: int,
) -> Optional[Dict[str, Any]]:
    if not isinstance(window, dict):
        return None
    used = window.get("used_percent")
    used_percent = float(used) if isinstance(used, (int, float)) else None
    reset_after = window.get("reset_after_seconds")
    reset_after_seconds = (
        int(reset_after) if isinstance(reset_after, (int, float)) else None
    )
    if reset_after_seconds is None:
        reset_at = window.get("reset_at")
        if isinstance(reset_at, (int, float)) and reset_at > 0:
            delta_seconds = int(float(reset_at) - time.time())
            if delta_seconds >= 0:
                reset_after_seconds = delta_seconds
    effective_limit_reached = bool(window.get("limit_reached"))
    if (
        not effective_limit_reached
        and limit_reached
        and used_percent is not None
        and used_percent >= cooldown_at
    ):
        effective_limit_reached = True
    status = classify_status(
        used_percent=used_percent,
        limit_reached=effective_limit_reached,
        warn_at=warn_at,
        cooldown_at=cooldown_at,
    )
    return {
        "status": status,
        "used_percent": used_percent,
        "reset_after_seconds": reset_after_seconds,
    }


def _numeric_value(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _message_estimates(value: Any) -> Optional[List[int]]:
    if not isinstance(value, list):
        return None
    result: List[int] = []
    for item in value:
        numeric = _numeric_value(item)
        if numeric is None:
            continue
        result.append(int(numeric))
    return result


def _message_estimates_have_remaining(value: Any) -> Optional[bool]:
    estimates = _message_estimates(value)
    if estimates is None:
        return None
    return any(item > 0 for item in estimates)


def credits_summary(credits: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(credits, dict):
        return None

    has_credits_raw = credits.get("has_credits")
    has_credits = (
        bool(has_credits_raw) if isinstance(has_credits_raw, bool) else None
    )
    unlimited = bool(credits.get("unlimited"))
    balance = _numeric_value(credits.get("balance"))
    approx_local_messages = _message_estimates(credits.get("approx_local_messages"))
    approx_cloud_messages = _message_estimates(credits.get("approx_cloud_messages"))

    status = "UNKNOWN"
    if unlimited:
        status = "OK"
    else:
        signals: List[bool] = []
        if has_credits is not None:
            signals.append(has_credits)
        if balance is not None:
            signals.append(balance > 0.0)
        local_remaining = _message_estimates_have_remaining(
            credits.get("approx_local_messages")
        )
        if local_remaining is not None:
            signals.append(local_remaining)
        cloud_remaining = _message_estimates_have_remaining(
            credits.get("approx_cloud_messages")
        )
        if cloud_remaining is not None:
            signals.append(cloud_remaining)

        if any(signals):
            status = "OK"
        elif signals:
            status = "EXHAUSTED"

    return {
        "status": status,
        "has_credits": has_credits,
        "unlimited": unlimited,
        "balance": balance,
        "approx_local_messages": approx_local_messages,
        "approx_cloud_messages": approx_cloud_messages,
    }


def live_usage_url(url: str) -> str:
    parsed = urlsplit(url)
    pairs = [
        (key, value)
        for (key, value) in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "_ts"
    ]
    pairs.append(("_ts", str(time.time_ns())))
    query = urlencode(pairs)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def fetch_usage(url: str, headers: Dict[str, str], timeout: int) -> Dict[str, Any]:
    live_url = live_usage_url(url)
    req_headers = dict(headers)
    req_headers.update(NO_CACHE_HEADERS)
    req = urllib.request.Request(live_url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def collective_health_snapshot(
    *,
    auths_dir: str,
    base_url: str,
    warn_at: int,
    cooldown_at: int,
    timeout: int,
    only: str,
    prefer_keyring: bool = True,
) -> Dict[str, Any]:
    accounts: List[Dict[str, Any]] = []
    usage_endpoint = usage_url(base_url)

    for auth in load_auth_records(auths_dir, prefer_keyring=prefer_keyring):
        headers = {
            "Authorization": f"Bearer {auth.token}",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if auth.account_id:
            headers["ChatGPT-Account-Id"] = str(auth.account_id)

        entry: Dict[str, Any] = {
            "file": auth.name,
            "email": auth.email,
            # NOTE: access_token intentionally NOT included to prevent token leakage
            "account_id": auth.account_id,
            "status": "UNKNOWN",
            "plan_type": None,
        }
        try:
            usage = fetch_usage(usage_endpoint, headers, timeout)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"usage fetch failed: {exc}"
            accounts.append(entry)
            continue

        rate_limit = usage.get("rate_limit") if isinstance(usage, dict) else None
        limits = extract_limits(rate_limit if isinstance(rate_limit, dict) else None)
        if only == "5h":
            limits["weekly"] = None
        elif only == "weekly":
            limits["five_hour"] = None
        limit_reached = bool((rate_limit or {}).get("limit_reached"))

        five_hour = window_summary(
            limits.get("five_hour"),
            limit_reached=limit_reached,
            warn_at=warn_at,
            cooldown_at=cooldown_at,
        )
        weekly = window_summary(
            limits.get("weekly"),
            limit_reached=limit_reached,
            warn_at=warn_at,
            cooldown_at=cooldown_at,
        )

        statuses: List[str] = []
        if five_hour:
            entry["five_hour"] = five_hour
            statuses.append(five_hour.get("status", "UNKNOWN"))
        if weekly:
            entry["weekly"] = weekly
            statuses.append(weekly.get("status", "UNKNOWN"))

        entry["status"] = overall_status(statuses) if statuses else "UNKNOWN"
        entry["plan_type"] = usage.get("plan_type") if isinstance(usage, dict) else None
        credit_health = (
            credits_summary(usage.get("credits")) if isinstance(usage, dict) else None
        )
        if credit_health is not None:
            entry["credits"] = credit_health
        entry["error"] = None
        accounts.append(entry)

    return {"accounts": accounts}
