from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet

from cdx_proxy_cli_v2.config.settings import resolve_path

# Exact field names that should never be logged.
SENSITIVE_FIELD_NAMES: FrozenSet[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "private_key",
        "session_key",
    }
)

# High-signal fragments that should remain redacted even inside compound names.
SENSITIVE_FIELD_SUBSTRINGS: FrozenSet[str] = frozenset(
    {
        "token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "private_key",
        "session_key",
    }
)


def _is_sensitive_field(field_name: str) -> bool:
    """Check if a field name matches a sensitive pattern."""
    normalized = str(field_name).lower().strip()
    if normalized in SENSITIVE_FIELD_NAMES:
        return True
    # Substring match for compound names like "user_token", "api_secret_key"
    for sensitive in SENSITIVE_FIELD_SUBSTRINGS:
        if sensitive in normalized:
            return True
    return False


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(sub) for key, sub in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return str(value)


class EventLogger:
    """Structured JSONL writer for operational proxy events.

    Automatically sanitizes sensitive fields before logging to prevent
    credential exposure in log files.
    """

    def __init__(self, auth_dir: str) -> None:
        self._path = resolve_path(auth_dir) / "rr_proxy_v2.events.jsonl"
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def write(
        self, *, level: str, event: str, message: str = "", **fields: Any
    ) -> None:
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": str(level).upper(),
            "event": str(event),
            "message": str(message),
        }
        for key, value in fields.items():
            # Sanitize sensitive fields
            if _is_sensitive_field(key):
                record[str(key)] = "[REDACTED]"
            else:
                record[str(key)] = _to_jsonable(value)
        raw = json.dumps(record, ensure_ascii=False)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(raw + "\n")


def tail_lines(path: Path, limit: int = 120) -> list[str]:
    if limit <= 0:
        limit = 120
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (FileNotFoundError, OSError):
        return []
    return lines[-limit:]
