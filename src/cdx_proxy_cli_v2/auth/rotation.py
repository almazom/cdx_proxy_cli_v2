from __future__ import annotations

import threading
import time
from typing import List, Optional

from cdx_proxy_cli_v2.auth.eligibility import limit_block_details
from cdx_proxy_cli_v2.auth.models import AuthRecord, AuthState

DEFAULT_COOLDOWN_SECONDS = 30
DEFAULT_TRANSIENT_COOLDOWN_SECONDS = 8
DEFAULT_BLACKLIST_SECONDS = 15 * 60
MAX_COOLDOWN_SECONDS = 15 * 60
MAX_BLACKLIST_SECONDS = 6 * 60 * 60
PROBATION_PROBE_INTERVAL_SECONDS = 20
PROBATION_SUCCESS_TARGET = 2
CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE = "chatgpt_account_incompatible"
AUTH_INCOMPATIBLE_ERROR_CODES = {CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE}
HARD_AUTH_BLACKLIST_REASONS = {"token_invalid", "forbidden"} | AUTH_INCOMPATIBLE_ERROR_CODES
SOFT_RESTORABLE_BLACKLIST_REASONS = {"rate_limited_persistent"}


def is_auth_incompatible_error(status: int, error_code: Optional[str] = None) -> bool:
    return int(status) == 400 and str(error_code or "").strip() in AUTH_INCOMPATIBLE_ERROR_CODES


def is_retryable_auth_failure(status: int, error_code: Optional[str] = None) -> bool:
    normalized_status = int(status)
    return normalized_status in {401, 403, 429} or is_auth_incompatible_error(normalized_status, error_code)


class RoundRobinAuthPool:
    """Thread-safe auth pool with cooldown, blacklist, and probation.
    
    Envoy-inspired features:
    - Outlier detection (blacklist on consecutive errors)
    - Active health checking (auto-heal background probes)
    - Max ejection percent (prevent total blackout)
    """

    def __init__(
        self,
        *,
        auto_heal_interval: int = 60,
        auto_heal_success_target: int = 2,
        auto_heal_max_attempts: int = 3,
        max_ejection_percent: int = 50,
        consecutive_error_threshold: int = 3,
    ) -> None:
        self._states: List[AuthState] = []
        self._index = 0
        self._lock = threading.Lock()
        # Auto-heal configuration (from Settings)
        self.auto_heal_interval = auto_heal_interval
        self.auto_heal_success_target = auto_heal_success_target
        self.auto_heal_max_attempts = auto_heal_max_attempts
        self.max_ejection_percent = max_ejection_percent
        self.consecutive_error_threshold = consecutive_error_threshold

    def load(self, records: List[AuthRecord]) -> None:
        with self._lock:
            previous = {state.record.name: state for state in self._states}
            next_states: List[AuthState] = []
            for record in records:
                state = AuthState(record=record)
                state.auto_heal_target = self.auto_heal_success_target
                prev = previous.get(record.name)
                if prev:
                    same_token = prev.record.token == record.token
                    state.used = prev.used
                    state.errors = prev.errors
                    if same_token:
                        state.cooldown_until = prev.cooldown_until
                        state.limit_until = prev.limit_until
                        state.limit_reason = prev.limit_reason
                        state.blacklist_until = prev.blacklist_until
                        state.blacklist_reason = prev.blacklist_reason
                        state.probation_successes = prev.probation_successes
                        state.probation_target = prev.probation_target
                        state.next_probe_after = prev.next_probe_after
                        state.rate_limit_strikes = prev.rate_limit_strikes
                        state.hard_failures = prev.hard_failures
                        state.auto_heal_successes = prev.auto_heal_successes
                        state.auto_heal_failures = prev.auto_heal_failures
                        state.auto_heal_last_check = prev.auto_heal_last_check
                        state.consecutive_errors = prev.consecutive_errors
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
        """Choose the next currently eligible auth from already-known state only."""
        with self._lock:
            now = time.time()
            available = [state for state in self._states if state.available(now)]

            # Envoy pattern: max ejection percent
            # Ensure we don't eject more than max_ejection_percent of keys
            total = len(self._states)
            max_ejected = int(total * max(0, self.max_ejection_percent) / 100)
            if self.max_ejection_percent < 100:
                max_ejected = min(max(total - 1, 0), max_ejected)
            else:
                max_ejected = total
            min_available = max(0, total - max_ejected)
            blacklisted_count = sum(
                1 for s in self._states
                if s.blacklist_until > now
            )
            
            # If we've hit max ejection, force-restore some keys
            if total > 1 and len(available) < min_available and blacklisted_count > 0:
                # Find blacklisted keys with least failures and restore them
                blacklisted = [
                    s for s in self._states
                    if s.blacklist_until > now
                    and s.blacklist_reason in SOFT_RESTORABLE_BLACKLIST_REASONS
                    and s not in available
                ]
                blacklisted.sort(key=lambda s: s.hard_failures)
                
                # Restore the least-failed keys
                to_restore = min(len(blacklisted), min_available - len(available))
                for state in blacklisted[:to_restore]:
                    state.blacklist_until = 0.0
                    state.blacklist_reason = None
                    state.cooldown_until = 0.0
                    state.probation_successes = state.probation_target
                    state.next_probe_after = 0.0
                    state.consecutive_errors = 0
                
                # Refresh available list
                available = [state for state in self._states if state.available(now)]

            if not available:
                return None
            
            # Latency-first policy: when at least one stable key exists,
            # avoid sending foreground traffic through previously hard-failed keys.
            preferred = [state for state in available if self._is_stable(state)]
            pool = preferred or available
            state = pool[self._index % len(pool)]
            self._index = (self._index + 1) % len(pool)
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
        force_blacklist: bool = False,
    ) -> None:
        with self._lock:
            now = time.time()
            for state in self._states:
                if state.record.name != auth_name:
                    continue
                if 200 <= int(status) < 400:
                    self._mark_success(state, now, auto_heal_target=self.auto_heal_success_target)
                    return

                if int(status) in {401, 403}:
                    state.consecutive_errors += 1
                    reason = error_code or ("token_invalid" if int(status) == 401 else "forbidden")
                    self._mark_blacklist(state, now, reason=reason)
                    return

                if is_auth_incompatible_error(int(status), error_code):
                    self._mark_blacklist(state, now, reason=str(error_code or "chatgpt_account_incompatible"))
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
    def _mark_success(state: AuthState, now: float, auto_heal_target: int = 2) -> None:
        state.cooldown_until = 0.0
        state.rate_limit_strikes = 0
        state.consecutive_errors = 0
        if state.probation_successes < state.probation_target:
            state.probation_successes += 1
            if state.probation_successes >= state.probation_target:
                state.blacklist_until = 0.0
                state.blacklist_reason = None
                state.next_probe_after = 0.0
        elif state.blacklist_until <= now:
            state.blacklist_reason = None
        
        # Auto-heal: track successful health check for blacklisted keys
        if state.blacklist_until > 0 and now < state.blacklist_until:
            state.auto_heal_successes += 1
            state.auto_heal_failures = 0
            state.auto_heal_last_check = now
            if state.auto_heal_successes >= auto_heal_target:
                # Restore key after successful auto-heal
                state.blacklist_until = 0.0
                state.blacklist_reason = None
                state.cooldown_until = 0.0
                state.auto_heal_successes = 0
                state.auto_heal_failures = 0

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
        state.consecutive_errors = 0
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
        state.consecutive_errors = 0
        state.cooldown_until = max(state.cooldown_until, now + DEFAULT_TRANSIENT_COOLDOWN_SECONDS)
    
    def _mark_auto_heal_failure(self, state: AuthState, now: float) -> None:
        """Track failed auto-heal health check."""
        state.auto_heal_failures += 1
        state.auto_heal_last_check = now
        # Reset success counter on failure
        state.auto_heal_successes = 0
        # If too many failures, extend blacklist
        if state.auto_heal_failures >= self.auto_heal_max_attempts:
            # Double the remaining blacklist time (capped at max)
            remaining = state.blacklist_until - now
            if remaining > 0:
                state.blacklist_until = min(
                    state.blacklist_until + remaining,
                    now + MAX_BLACKLIST_SECONDS
                )
            state.auto_heal_failures = 0
    
    def mark_auto_heal_failure(self, auth_name: str, now: float) -> None:
        """Public method to track failed auto-heal check by auth name."""
        with self._lock:
            for state in self._states:
                if state.record.name == auth_name:
                    self._mark_auto_heal_failure(state, now)
                    return

    def apply_limit_health(self, limit_health_by_file: dict[str, dict]) -> None:
        with self._lock:
            for state in self._states:
                limit_health = limit_health_by_file.get(state.record.name) or {}
                block = limit_block_details(limit_health)
                if not block:
                    state.limit_until = 0.0
                    state.limit_reason = None
                    continue
                state.limit_until = float(block["until"])
                state.limit_reason = str(block["reason"])

    @staticmethod
    def _is_stable(state: AuthState) -> bool:
        return (
            state.hard_failures <= 0
            and state.rate_limit_strikes <= 0
            and state.probation_successes >= state.probation_target
        )

    def reset_auth(
        self,
        *,
        name: Optional[str] = None,
        state: Optional[str] = None,
    ) -> int:
        """Reset auth key(s) to healthy state.

        Args:
            name: If specified, only reset the auth with this file name.
            state: If specified, only reset auths in this state 
                   ("blacklist", "cooldown", or "probation").

        Returns:
            Number of auth keys that were reset.
        """
        with self._lock:
            now = time.time()
            count = 0
            for auth_state in self._states:
                # Filter by name if specified
                if name is not None and auth_state.record.name != name:
                    continue

                # Filter by state if specified
                if state is not None:
                    current_status = auth_state.status(now).lower()
                    if current_status != state.lower():
                        continue

                # Reset all failure counters and timers
                auth_state.cooldown_until = 0.0
                auth_state.blacklist_until = 0.0
                auth_state.blacklist_reason = None
                auth_state.rate_limit_strikes = 0
                auth_state.hard_failures = 0
                auth_state.errors = 0
                auth_state.consecutive_errors = 0
                auth_state.auto_heal_successes = 0
                auth_state.auto_heal_failures = 0
                auth_state.auto_heal_last_check = 0.0
                auth_state.probation_successes = auth_state.probation_target
                auth_state.next_probe_after = 0.0
                count += 1

            return count
