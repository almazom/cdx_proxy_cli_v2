from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from cdx_proxy_cli_v2.config.settings import resolve_path
from cdx_proxy_cli_v2.observability.event_log import _is_sensitive_field, _to_jsonable

_WRITE_LOCK = threading.Lock()


def latest_limits_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "rr_proxy_v2.limits.json"


def limits_history_path(auth_dir: str) -> Path:
    return resolve_path(auth_dir) / "rr_proxy_v2.limits.jsonl"


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if _is_sensitive_field(normalized_key):
                sanitized[normalized_key] = "[REDACTED]"
            else:
                sanitized[normalized_key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return _to_jsonable(value)


def _history_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    fetched_at = payload.get("fetched_at")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        return []
    records: List[Dict[str, Any]] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        records.append(
            {
                "ts": fetched_at,
                "fetched_at": fetched_at,
                "file": account.get("file"),
                "email": account.get("email"),
                "status": account.get("status"),
                "reason": account.get("reason"),
                "reason_origin": account.get("reason_origin"),
                "cooldown_seconds": account.get("cooldown_seconds"),
                "five_hour": account.get("five_hour"),
                "weekly": account.get("weekly"),
            }
        )
    return records


def read_latest_limits_snapshot(auth_dir: str) -> Dict[str, Any]:
    path = latest_limits_path(auth_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return _sanitize_value(raw)


def write_latest_limits_snapshot(auth_dir: str, payload: Dict[str, Any]) -> None:
    path = latest_limits_path(auth_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_value(payload)
    raw = json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with _WRITE_LOCK:
        tmp_path.write_text(raw, encoding="utf-8")
        tmp_path.replace(path)


def append_limits_history(auth_dir: str, payload: Dict[str, Any]) -> None:
    path = limits_history_path(auth_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = _history_records(_sanitize_value(payload))
    if not records:
        return
    raw = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(raw)
