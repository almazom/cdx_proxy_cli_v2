from __future__ import annotations

import threading
from collections import deque
from typing import Any, Deque, Dict, List


class TraceStore:
    """In-memory ring buffer for request trace events."""

    def __init__(self, max_size: int = 500) -> None:
        self._max_size = max(1, int(max_size))
        self._items: Deque[Dict[str, Any]] = deque(maxlen=self._max_size)
        self._seq = 0
        self._lock = threading.Lock()

    def add(self, event: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._seq += 1
            payload = dict(event)
            payload["id"] = self._seq
            self._items.append(payload)
            return payload

    def list(self, limit: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._items)
        if limit > 0:
            return items[-limit:]
        return items

    @property
    def max_size(self) -> int:
        return self._max_size
