from __future__ import annotations

import logging
import random
import threading
import time
from typing import List, Optional

from cdx_proxy_cli_v2.auth.eligibility import limit_block_details
from cdx_proxy_cli_v2.auth.models import AuthRecord, AuthState
from cdx_proxy_cli_v2.config.settings import DEFAULT_SMALL_POOL_AUTO_RESET_KEY_COUNT

DEFAULT_COOLDOWN_SECONDS = 30
DEFAULT_TRANSIENT_COOLDOWN_SECONDS = 8
DEFAULT_BLACKLIST_SECONDS = 15 * 60
MAX_COOLDOWN_SECONDS = 15 * 60
MAX_BLACKLIST_SECONDS = 6 * 60 * 60
PROBATION_PROBE_INTERVAL_SECONDS = 20
PROBATION_SUCCESS_TARGET = 2
CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE = "chatgpt_account_incompatible"
AUTH_INCOMPATIBLE_ERROR_CODES = {CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE}
HARD_AUTH_BLACKLIST_REASONS = {
    "token_invalid",
    "forbidden",
    "subscription_expired",
} | AUTH_INCOMPATIBLE_ERROR_CODES
logger = logging.getLogger(__name__)


def is_auth_incompatible_error(status: int, error_code: Optional[str] = None) -> bool:
    return (
        int(status) == 400
        and str(error_code or "").strip() in AUTH_INCOMPATIBLE_ERROR_CODES
    )


def is_retryable_auth_failure(status: int, error_code: Optional[str] = None) -> bool:
    normalized_status = int(status)
    return normalized_status in {401, 403, 429} or is_auth_incompatible_error(
        normalized_status, error_code
    )


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
        auto_reset_on_single_key: bool = False,
        auto_reset_on_single_key_explicit: bool = False,
        auto_reset_streak: int = 4,
        auto_reset_cooldown: int = 120,
        auto_heal_interval: int = 60,
        auto_heal_success_target: int = 2,
        auto_heal_max_attempts: int = 3,
        max_ejection_percent: int = 50,
        consecutive_error_threshold: int = 3,
    ) -> None:
        self._states: List[AuthState] = []
        self._index = 0
        self._lock = threading.Lock()
        self._random = random.Random()
        self._configured_auto_reset_on_single_key = bool(auto_reset_on_single_key)
        self._auto_reset_on_single_key_explicit = bool(
            auto_reset_on_single_key_explicit
        )
        self.auto_reset_on_single_key = bool(auto_reset_on_single_key)
        self.auto_reset_streak = max(1, int(auto_reset_streak))
        self.auto_reset_cooldown = max(1, int(auto_reset_cooldown))
        self._recent_pick_names: List[str] = []
        self._recent_pick_index = 0
        self.last_auto_reset_time = 0.0
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
                    state.last_picked_at = prev.last_picked_at
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
                        state.remaining_capacity_weight = (
                            prev.remaining_capacity_weight
                        )
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
            self.auto_reset_on_single_key = self._configured_auto_reset_on_single_key or (
                not self._auto_reset_on_single_key_explicit
                and 0 < len(self._states) <= DEFAULT_SMALL_POOL_AUTO_RESET_KEY_COUNT
            )
            self._recent_pick_names = [""] * self.auto_reset_streak
            self._recent_pick_index = 0
            if self._states:
                self._index %= len(self._states)
            else:
                self._index = 0

    @staticmethod
    def _normalize_allowed_names(
        allowed_names: Optional[set[str]],
    ) -> Optional[set[str]]:
        if allowed_names is None:
            return None
        return {str(name).strip() for name in allowed_names if str(name).strip()}

    def pick(self, *, allowed_names: Optional[set[str]] = None) -> Optional[AuthState]:
        """Choose the next currently eligible auth from already-known state only."""
        with self._lock:
            now = time.time()
            self._restore_stable_state_after_cooldown(now, self._states)
            allowed = self._normalize_allowed_names(allowed_names)
            available = [
                state
                for state in self._states
                if state.available(now)
                and (allowed is None or state.record.name in allowed)
            ]

            if not available:
                return None

            # Latency-first policy: when at least one stable key exists,
            # avoid sending foreground traffic through previously hard-failed keys.
            preferred = [state for state in available if self._is_stable(state)]
            pool = preferred or available
            state = self._pick_from_pool(pool)
            if state is None:
                return None
            state.used += 1
            state.last_picked_at = now
            if state.probation_successes < state.probation_target:
                state.next_probe_after = now + PROBATION_PROBE_INTERVAL_SECONDS
            return state

    def count(self) -> int:
        with self._lock:
            return len(self._states)

    def preview_next_pick(
        self, *, allowed_names: Optional[set[str]] = None
    ) -> Optional[dict]:
        """Return the next auth that would be picked without mutating pool state."""
        with self._lock:
            now = time.time()
            self._restore_stable_state_after_cooldown(now, self._states)
            allowed = self._normalize_allowed_names(allowed_names)
            available = [
                state
                for state in self._states
                if state.available(now)
                and (allowed is None or state.record.name in allowed)
            ]
            if not available:
                return None

            preferred = [state for state in available if self._is_stable(state)]
            pool = preferred or available
            candidate = self._preview_pool_pick(pool)
            if candidate is not None:
                return {
                    "file": candidate.record.name,
                    "email": candidate.record.email,
                }
            return None

    def mark_cooldown(
        self, auth_name: str, seconds: int = DEFAULT_COOLDOWN_SECONDS
    ) -> None:
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
                if 100 <= int(status) < 400:
                    self._mark_success(
                        state, now, auto_heal_target=self.auto_heal_success_target
                    )
                    return

                if int(status) in {401, 403}:
                    reason = error_code or (
                        "token_invalid" if int(status) == 401 else "forbidden"
                    )
                    if error_code == "subscription_expired":
                        reason = "subscription_expired"
                    self._mark_hard_auth_failure(state, now, reason=reason)
                    return

                if is_auth_incompatible_error(int(status), error_code):
                    self._mark_blacklist(
                        state,
                        now,
                        reason=str(error_code or "chatgpt_account_incompatible"),
                    )
                    return

                if int(status) == 429:
                    self._mark_rate_limited(
                        state,
                        now,
                        seconds_override=(
                            max(1, int(cooldown_seconds))
                            if cooldown_seconds is not None
                            else None
                        ),
                    )
                    return

                if int(status) >= 500 or int(status) in {408, 409, 425}:
                    self._mark_transient_failure(state, now)
                    return

                # Client/request-side 4xx that are not auth/limit signals should not poison the key.
                state.consecutive_errors = 0
                return

    def health_snapshot(self) -> List[dict]:
        with self._lock:
            now = time.time()
            return [state.health(now) for state in self._states]

    def selection_snapshot(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "file": state.record.name,
                    "weight": float(state.remaining_capacity_weight),
                    "last_picked_at": float(state.last_picked_at),
                }
                for state in self._states
            ]

    def load_from_snapshot(self, snapshot: dict[str, dict], now: float) -> int:
        restored = 0
        with self._lock:
            for state in self._states:
                entry = snapshot.get(state.record.name)
                if not isinstance(entry, dict):
                    continue
                cooldown_until = float(entry.get("cooldown_until") or 0.0)
                if cooldown_until > now:
                    state.cooldown_until = cooldown_until
                limit_until = float(entry.get("limit_until") or 0.0)
                if limit_until > now:
                    state.limit_until = limit_until
                    state.limit_reason = entry.get("limit_reason")
                blacklist_until = float(entry.get("blacklist_until") or 0.0)
                if blacklist_until > now:
                    state.blacklist_until = blacklist_until
                    state.blacklist_reason = entry.get("blacklist_reason")
                    state.next_probe_after = blacklist_until
                state.rate_limit_strikes = int(entry.get("rate_limit_strikes") or 0)
                state.hard_failures = int(entry.get("hard_failures") or 0)
                state.consecutive_errors = int(entry.get("consecutive_errors") or 0)
                state.probation_successes = int(entry.get("probation_successes") or 0)
                state.probation_target = int(
                    entry.get("probation_target") or PROBATION_SUCCESS_TARGET
                )
                state.last_picked_at = float(entry.get("last_picked_at") or 0.0)
                restored += 1
        return restored

    def auth_files(self) -> List[str]:
        with self._lock:
            return [state.record.name for state in self._states]

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            counts = {
                "ok": 0,
                "cooldown": 0,
                "blacklist": 0,
                "probation": 0,
                "total": len(self._states),
            }
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
                state.hard_failures = 0
        elif state.blacklist_until <= now:
            state.blacklist_reason = None
            state.hard_failures = 0

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
                state.hard_failures = 0

    def _mark_hard_auth_failure(
        self, state: AuthState, now: float, *, reason: str
    ) -> None:
        state.consecutive_errors += 1
        threshold = max(1, int(self.consecutive_error_threshold))
        if state.consecutive_errors >= threshold:
            self._mark_blacklist(state, now, reason=reason)
            return
        state.errors += 1
        state.cooldown_until = max(
            state.cooldown_until, now + DEFAULT_TRANSIENT_COOLDOWN_SECONDS
        )

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
        cooldown = (
            seconds_override
            if seconds_override is not None
            else self._rate_limit_cooldown_seconds(state.rate_limit_strikes)
        )
        state.cooldown_until = max(state.cooldown_until, now + max(1, int(cooldown)))
        # Persistent 429s are ejected temporarily as outliers.
        if state.rate_limit_strikes >= 5:
            self._mark_blacklist(state, now, reason="rate_limited_persistent")

    def _mark_blacklist(self, state: AuthState, now: float, *, reason: str) -> None:
        total_count = len(self._states)
        max_ejection_ratio = max(0, int(self.max_ejection_percent)) / 100.0
        blacklisted_count = sum(1 for item in self._states if item.blacklist_until > now)
        if (
            total_count > 1
            and max_ejection_ratio < 1.0
            and state.blacklist_until <= now
            and ((blacklisted_count + 1) / total_count) > max_ejection_ratio
        ):
            state.errors += 1
            state.consecutive_errors = 0
            state.cooldown_until = max(
                state.cooldown_until, now + DEFAULT_TRANSIENT_COOLDOWN_SECONDS
            )
            logger.warning(
                "Skipping blacklist for %s: max_ejection_percent=%s would be exceeded",
                state.record.name,
                self.max_ejection_percent,
            )
            return

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
        state.cooldown_until = max(
            state.cooldown_until, now + DEFAULT_TRANSIENT_COOLDOWN_SECONDS
        )

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
                    state.blacklist_until + remaining, now + MAX_BLACKLIST_SECONDS
                )
            state.auto_heal_failures = 0

    def mark_auto_heal_failure(self, auth_name: str, now: float) -> None:
        """Public method to track failed auto-heal check by auth name."""
        with self._lock:
            for state in self._states:
                if state.record.name == auth_name:
                    self._mark_auto_heal_failure(state, now)
                    return

    def _pick_from_pool(self, pool: List[AuthState]) -> Optional[AuthState]:
        if self._weights_are_uniform(pool):
            return self._pick_round_robin(pool, advance_index=True)
        weighted_pool = self._build_weighted_pool(pool)
        if not weighted_pool:
            return None
        total_weight = weighted_pool[-1][1]
        if total_weight <= 0.0:
            state = pool[0]
            self._advance_index_past(state)
            return state
        draw = self._random.random() * total_weight
        for state, cumulative_weight in weighted_pool:
            if draw < cumulative_weight:
                self._advance_index_past(state)
                return state
        state = weighted_pool[-1][0]
        self._advance_index_past(state)
        return state

    def _preview_pool_pick(self, pool: List[AuthState]) -> Optional[AuthState]:
        if self._weights_are_uniform(pool):
            return self._pick_round_robin(pool, advance_index=False)
        weighted_pool = self._build_weighted_pool(pool)
        if not weighted_pool:
            return None
        total_weight = weighted_pool[-1][1]
        if total_weight <= 0.0:
            return pool[0]
        random_state = self._random.getstate()
        try:
            draw = self._random.random() * total_weight
        finally:
            self._random.setstate(random_state)
        for state, cumulative_weight in weighted_pool:
            if draw < cumulative_weight:
                return state
        return weighted_pool[-1][0]

    @staticmethod
    def _build_weighted_pool(
        pool: List[AuthState],
    ) -> list[tuple[AuthState, float]]:
        weighted_pool: list[tuple[AuthState, float]] = []
        total_weight = 0.0
        for state in pool:
            total_weight += max(0.0, float(state.remaining_capacity_weight))
            weighted_pool.append((state, total_weight))
        return weighted_pool

    @staticmethod
    def _weights_are_uniform(pool: List[AuthState]) -> bool:
        if len(pool) <= 1:
            return True
        first = max(0.0, float(pool[0].remaining_capacity_weight))
        for state in pool[1:]:
            if abs(max(0.0, float(state.remaining_capacity_weight)) - first) > 1e-9:
                return False
        return True

    def _pick_round_robin(
        self,
        pool: List[AuthState],
        *,
        advance_index: bool,
    ) -> Optional[AuthState]:
        pool_ids = {id(candidate) for candidate in pool}
        for offset in range(len(self._states)):
            idx = (self._index + offset) % len(self._states)
            candidate = self._states[idx]
            if id(candidate) not in pool_ids:
                continue
            if advance_index:
                self._index = (idx + 1) % len(self._states)
            return candidate
        return None

    def _advance_index_past(self, state: AuthState) -> None:
        for idx, candidate in enumerate(self._states):
            if candidate is state:
                self._index = (idx + 1) % len(self._states)
                return

    @staticmethod
    def _remaining_capacity_weight(limit_health: dict[str, dict]) -> float:
        for window_name in ("five_hour", "weekly"):
            window = limit_health.get(window_name) or {}
            used_percent = window.get("used_percent")
            if used_percent is None:
                continue
            remaining = 100.0 - float(used_percent)
            return max(0.1, remaining / 100.0)
        return 1.0

    def apply_limit_health(
        self,
        limit_health_by_file: dict[str, dict],
        *,
        min_remaining_percent: float,
    ) -> None:
        with self._lock:
            for state in self._states:
                limit_health = limit_health_by_file.get(state.record.name) or {}
                state.remaining_capacity_weight = self._remaining_capacity_weight(
                    limit_health
                )
                block = limit_block_details(
                    limit_health,
                    min_remaining_percent=min_remaining_percent,
                )
                if not block:
                    state.limit_until = 0.0
                    state.limit_reason = None
                    continue
                state.limit_until = float(block["until"])
                state.limit_reason = str(block["reason"])

    @staticmethod
    def _restore_stable_state_after_cooldown(
        now: float, states: Optional[List[AuthState]] = None
    ) -> None:
        active_states = states or []
        for state in active_states:
            if state.cooldown_until > now:
                continue
            if state.blacklist_until > now:
                continue
            if state.probation_successes < state.probation_target:
                continue
            if state.rate_limit_strikes > 0:
                state.rate_limit_strikes = 0

    @staticmethod
    def _is_stable(state: AuthState) -> bool:
        return (
            state.hard_failures <= 0
            and state.rate_limit_strikes <= 0
            and state.probation_successes >= state.probation_target
        )

    @staticmethod
    def _reset_state(auth_state: AuthState) -> None:
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

    def maybe_auto_reset_single_key(self, picked_name: str, now: float) -> int:
        with self._lock:
            if not self.auto_reset_on_single_key:
                return 0

            normalized_name = str(picked_name).strip()
            if not normalized_name:
                return 0

            if not self._recent_pick_names:
                self._recent_pick_names = [""] * self.auto_reset_streak
                self._recent_pick_index = 0
            self._recent_pick_names[self._recent_pick_index] = normalized_name
            self._recent_pick_index = (self._recent_pick_index + 1) % self.auto_reset_streak

            if "" in self._recent_pick_names:
                return 0
            if any(name != normalized_name for name in self._recent_pick_names):
                return 0
            if (now - self.last_auto_reset_time) < float(self.auto_reset_cooldown):
                return 0

            reset_count = 0
            for auth_state in self._states:
                if auth_state.record.name == normalized_name:
                    continue
                status = self._resettable_status(auth_state, now)
                if status not in {"BLACKLIST", "PROBATION"}:
                    continue
                self._reset_state(auth_state)
                reset_count += 1

            if reset_count > 0:
                self.last_auto_reset_time = now
            return reset_count

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
                    current_status = self._resettable_status(auth_state, now).lower()
                    if current_status != state.lower():
                        continue

                self._reset_state(auth_state)
                count += 1

            return count

    @staticmethod
    def _resettable_status(auth_state: AuthState, now: float) -> str:
        """Return only runtime states that reset_auth can actually clear."""
        if auth_state.blacklist_until > now:
            return "BLACKLIST"
        if auth_state.cooldown_until > now:
            return "COOLDOWN"
        if auth_state.probation_successes < auth_state.probation_target:
            return "PROBATION"
        return "OK"
