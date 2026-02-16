from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from cdx_proxy_cli_v2.config.settings import resolve_path


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
    """Structured JSONL writer for operational proxy events."""

    def __init__(self, auth_dir: str) -> None:
        self._path = resolve_path(auth_dir) / "rr_proxy_v2.events.jsonl"
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def write(self, *, level: str, event: str, message: str = "", **fields: Any) -> None:
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": str(level).upper(),
            "event": str(event),
            "message": str(message),
        }
        for key, value in fields.items():
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
