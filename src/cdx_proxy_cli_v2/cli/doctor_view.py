from __future__ import annotations

from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table

DOCTOR_ACTION_DESCRIPTIONS = {
    "healthy": "Probe succeeded; runtime state unchanged",
    "would_cooldown": "Probe hit 429; key would enter cooldown if used live",
    "auth_failed": "Probe hit 401/403; auth looks unhealthy",
    "compat_failed": "Probe saw account/provider incompatibility",
    "error": "Probe got a non-auth HTTP error",
    "network_error": "Probe failed before getting an HTTP response",
}


def _state_bucket(status: object) -> str:
    normalized = str(status or "UNKNOWN").upper()
    if normalized in {"OK", "WARN"}:
        return "whitelist"
    if normalized == "PROBATION":
        return "probation"
    if normalized == "COOLDOWN":
        return "cooldown"
    if normalized == "BLACKLIST":
        return "blacklist"
    return "unknown"


def _extract_accounts(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    accounts_raw = payload.get("accounts", [])
    if not isinstance(accounts_raw, list):
        return []
    return [item for item in accounts_raw if isinstance(item, dict)]


def _summarize_accounts(accounts: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "whitelist": 0,
        "probation": 0,
        "cooldown": 0,
        "blacklist": 0,
        "unknown": 0,
        "total": len(accounts),
    }
    for item in accounts:
        summary[_state_bucket(item.get("status"))] += 1
    return summary


def _doctor_payload(
    *, base_url: str, accounts: List[Dict[str, Any]], policy: Dict[str, Any], probe: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": True,
        "base_url": base_url,
        "policy": dict(policy),
        "summary": _summarize_accounts(accounts),
        "accounts": accounts,
    }
    if probe is not None:
        payload["probe"] = probe
    return payload


def _render_probe_results(probe_payload: Dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        return

    results = probe_payload.get("results", [])
    probed = probe_payload.get("probed", 0)
    action_counts: Dict[str, int] = {}
    for record in results:
        action = record.get("action", "none")
        action_counts[action] = action_counts.get(action, 0) + 1

    print(f"Probed {probed} auth key(s)")
    print()
    if action_counts:
        print("Probe outcomes:")
        for action, count in sorted(action_counts.items()):
            print(
                f"  {action}: {count} ({DOCTOR_ACTION_DESCRIPTIONS.get(action, action)})"
            )
        print()

    notable_results = [item for item in results if item.get("action") != "healthy"]
    if not notable_results:
        return

    table = Table(title="cdx doctor | probe findings")
    table.add_column("File")
    table.add_column("Previous")
    table.add_column("Current")
    table.add_column("Action")
    table.add_column("HTTP")
    table.add_column("Latency")
    for record in sorted(notable_results, key=lambda item: str(item.get("file", ""))):
        latency_ms = record.get("latency_ms", 0)
        http_status = record.get("http_status")
        http_str = str(http_status) if http_status is not None else "-"
        table.add_row(
            str(record.get("file") or "-"),
            str(record.get("previous_status") or "-"),
            str(record.get("status") or "-"),
            str(record.get("action") or "-"),
            http_str,
            f"{latency_ms}ms",
        )
    Console().print(table)
    print()


def _render_doctor_table(accounts: List[Dict[str, Any]], summary: Dict[str, int]) -> None:
    table = Table(title="cdx doctor | auth rotation state")
    table.add_column("File")
    table.add_column("Status")
    table.add_column("Cooldown")
    table.add_column("Blacklist")
    table.add_column("Probation")
    table.add_column("Used")
    table.add_column("Errors")
    table.add_column("Reason")
    for item in sorted(accounts, key=lambda row: str(row.get("file") or "")):
        table.add_row(
            str(item.get("file") or "-"),
            str(item.get("status") or "UNKNOWN"),
            str(item.get("cooldown_seconds") or "-"),
            str(item.get("blacklist_seconds") or "-"),
            f"{item.get('probation_successes')}/{item.get('probation_target')}"
            if item.get("probation")
            else "-",
            str(item.get("used") or 0),
            str(item.get("errors") or 0),
            str(item.get("blacklist_reason") or "-"),
        )
    Console().print(table)
    print(
        "Summary: "
        f"white={summary['whitelist']} probation={summary['probation']} "
        f"cooldown={summary['cooldown']} black={summary['blacklist']} unknown={summary['unknown']}"
    )
    print(
        "Policy: 401/403 -> blacklist, 429 -> exponential cooldown, re-entry via probation"
    )
