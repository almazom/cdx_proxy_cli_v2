from __future__ import annotations

import threading
import time
from typing import List, Optional

from cdx_proxy_cli_v2.auth.models import AuthRecord, AuthState

DEFAULT_COOLDOWN_SECONDS = 30
DEFAULT_TRANSIENT_COOLDOWN_SECONDS = 8
DEFAULT_BLACKLIST_SECONDS = 15 * 60
MAX_COOLDOWN_SECONDS = 15 * 60
MAX_BLACKLIST_SECONDS = 6 * 60 * 60
PROBATION_PROBE_INTERVAL_SECONDS = 20
PROBATION_SUCCESS_TARGET = 2


class RoundRobinAuthPool:
    """Thread-safe auth pool with cooldown, blacklist, and probation."""

    def __init__(self) -> None:
        self._states: List[AuthState] = []
        self._index = 0
        self._lock = threading.Lock()

    def load(self, records: List[AuthRecord]) -> None:
        with self._lock:
            previous = {state.record.name: state for state in self._states}
            next_states: List[AuthState] = []
            for record in records:
                state = AuthState(record=record)
                prev = previous.get(record.name)
                if prev:
                    same_token = prev.record.token == record.token
                    state.used = prev.used
                    state.errors = prev.errors
                    if same_token:
                        state.cooldown_until = prev.cooldown_until
                        state.blacklist_until = prev.blacklist_until
                        state.blacklist_reason = prev.blacklist_reason
                        state.probation_successes = prev.probation_successes
                        state.probation_target = prev.probation_target
                        state.next_probe_after = prev.next_probe_after
                        state.rate_limit_strikes = prev.rate_limit_strikes
                        state.hard_failures = prev.hard_failures
                    else:
                        # Fresh token replaces previous penalties.
                        state.probation_successes = PROBATION_SUCCESS_TARGET
                        state.probation_target = PROBATION_SUCCESS_TARGET
                next_states.append(state)
            self._states = next_states
            if self._states:
                self._index %= len(self._states)
            else:
                self._index = 0

    def pick(self) -> Optional[AuthState]:
        with self._lock:
            now = time.time()
            available = [state for state in self._states if state.available(now)]
            if not available:
                return None
            state = available[self._index % len(available)]
            self._index = (self._index + 1) % len(available)
            state.used += 1
            if state.probation_successes < state.probation_target:
                state.next_probe_after = now + PROBATION_PROBE_INTERVAL_SECONDS
            return state

    def count(self) -> int:
        with self._lock:
            return len(self._states)

    def mark_cooldown(self, auth_name: str, seconds: int = DEFAULT_COOLDOWN_SECONDS) -> None:
        # Legacy helper kept for compatibility with older call-sites.
        self.mark_result(auth_name, status=429, cooldown_seconds=seconds)

    def mark_result(
        self,
        auth_name: str,
        *,
        status: int,
        error_code: Optional[str] = None,
        cooldown_seconds: Optional[int] = None,
    ) -> None:
        with self._lock:
            now = time.time()
            for state in self._states:
                if state.record.name != auth_name:
                    continue
                if 200 <= int(status) < 400:
                    self._mark_success(state, now)
                    return

                if int(status) in {401, 403}:
                    reason = error_code or ("token_invalid" if int(status) == 401 else "forbidden")
                    self._mark_blacklist(state, now, reason=reason)
                    return

                if int(status) == 429:
                    self._mark_rate_limited(
                        state,
                        now,
                        seconds_override=(max(1, int(cooldown_seconds)) if cooldown_seconds is not None else None),
                    )
                    return

                if int(status) >= 500 or int(status) in {408, 409, 425}:
                    self._mark_transient_failure(state, now)
                    return

                # Unknown non-success status: mild cooldown only.
                self._mark_transient_failure(state, now)
                return

    def health_snapshot(self) -> List[dict]:
        with self._lock:
            now = time.time()
            return [state.health(now) for state in self._states]

    def auth_files(self) -> List[str]:
        with self._lock:
            return [state.record.name for state in self._states]

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            counts = {"ok": 0, "cooldown": 0, "blacklist": 0, "probation": 0, "total": len(self._states)}
            for state in self._states:
                status = state.status(now)
                if status == "OK":
                    counts["ok"] += 1
                elif status == "COOLDOWN":
                    counts["cooldown"] += 1
                elif status == "PROBATION":
                    counts["probation"] += 1
                else:
                    counts["blacklist"] += 1
            return counts

    @staticmethod
    def _mark_success(state: AuthState, now: float) -> None:
        state.cooldown_until = 0.0
        state.rate_limit_strikes = 0
        if state.probation_successes < state.probation_target:
            state.probation_successes += 1
            if state.probation_successes >= state.probation_target:
                state.blacklist_until = 0.0
                state.blacklist_reason = None
                state.next_probe_after = 0.0
        elif state.blacklist_until <= now:
            state.blacklist_reason = None

    @staticmethod
    def _rate_limit_cooldown_seconds(strikes: int) -> int:
        power = min(max(strikes - 1, 0), 6)
        return min(MAX_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS * (2**power))

    def _mark_rate_limited(
        self,
        state: AuthState,
        now: float,
        *,
        seconds_override: Optional[int] = None,
    ) -> None:
        state.errors += 1
        state.rate_limit_strikes += 1
        cooldown = seconds_override if seconds_override is not None else self._rate_limit_cooldown_seconds(state.rate_limit_strikes)
        state.cooldown_until = max(state.cooldown_until, now + max(1, int(cooldown)))
        # Persistent 429s are ejected temporarily as outliers.
        if state.rate_limit_strikes >= 5:
            self._mark_blacklist(state, now, reason="rate_limited_persistent")

    def _mark_blacklist(self, state: AuthState, now: float, *, reason: str) -> None:
        state.errors += 1
        state.hard_failures += 1
        ttl_power = min(max(state.hard_failures - 1, 0), 4)
        ttl = min(MAX_BLACKLIST_SECONDS, DEFAULT_BLACKLIST_SECONDS * (2**ttl_power))
        state.blacklist_until = max(state.blacklist_until, now + max(1, int(ttl)))
        state.blacklist_reason = reason
        state.probation_target = PROBATION_SUCCESS_TARGET
        state.probation_successes = 0
        state.next_probe_after = state.blacklist_until
        state.cooldown_until = max(state.cooldown_until, state.blacklist_until)

    @staticmethod
    def _mark_transient_failure(state: AuthState, now: float) -> None:
        state.errors += 1
        state.cooldown_until = max(state.cooldown_until, now + DEFAULT_TRANSIENT_COOLDOWN_SECONDS)
