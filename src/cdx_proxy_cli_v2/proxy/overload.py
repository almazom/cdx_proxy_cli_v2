from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class RequestLease:
    _guard: Optional["LocalOverloadGuard"]
    admitted: bool
    queued: bool
    in_flight: int
    pending: int

    def __enter__(self) -> "RequestLease":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.release()

    def release(self) -> None:
        guard = self._guard
        if guard is None:
            return
        self._guard = None
        guard.release()


class LocalOverloadGuard:
    """Bound concurrent request pressure before auth selection begins."""

    def __init__(
        self,
        *,
        max_in_flight_requests: int = 0,
        max_pending_requests: int = 0,
    ) -> None:
        self.max_in_flight_requests = max(0, int(max_in_flight_requests))
        self.max_pending_requests = max(0, int(max_pending_requests))
        self._condition = threading.Condition()
        self._in_flight_requests = 0
        self._pending_requests = 0

    def acquire(self) -> RequestLease:
        with self._condition:
            if (
                self.max_in_flight_requests <= 0
                or self._in_flight_requests < self.max_in_flight_requests
            ):
                self._in_flight_requests += 1
                return RequestLease(
                    _guard=self,
                    admitted=True,
                    queued=False,
                    in_flight=self._in_flight_requests,
                    pending=self._pending_requests,
                )

            if self._pending_requests >= self.max_pending_requests:
                return RequestLease(
                    _guard=None,
                    admitted=False,
                    queued=False,
                    in_flight=self._in_flight_requests,
                    pending=self._pending_requests,
                )

            self._pending_requests += 1
            try:
                while self._in_flight_requests >= self.max_in_flight_requests:
                    self._condition.wait()
                self._pending_requests -= 1
                self._in_flight_requests += 1
                return RequestLease(
                    _guard=self,
                    admitted=True,
                    queued=True,
                    in_flight=self._in_flight_requests,
                    pending=self._pending_requests,
                )
            except Exception:
                self._pending_requests -= 1
                self._condition.notify_all()
                raise

    def release(self) -> None:
        with self._condition:
            if self._in_flight_requests > 0:
                self._in_flight_requests -= 1
            self._condition.notify()

    def snapshot(self) -> dict[str, int]:
        with self._condition:
            return {
                "in_flight_requests": self._in_flight_requests,
                "pending_requests": self._pending_requests,
                "max_in_flight_requests": self.max_in_flight_requests,
                "max_pending_requests": self.max_pending_requests,
            }
