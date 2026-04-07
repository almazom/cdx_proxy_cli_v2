from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AuthRecord:
    name: str
    path: str
    token: str
    email: Optional[str] = None
    account_id: Optional[str] = None


@dataclass
class AuthState:
    record: AuthRecord
    cooldown_until: float = 0.0
    limit_until: float = 0.0
    limit_reason: Optional[str] = None
    selection_limit_known: bool = False
    selection_preferred: bool = False
    selection_remaining_percent: Optional[float] = None
    selection_reset_after_seconds: Optional[int] = None
    selection_floor_percent: Optional[float] = None
    blacklist_until: float = 0.0
    blacklist_reason: Optional[str] = None
    probation_successes: int = 2
    probation_target: int = 2
    next_probe_after: float = 0.0
    used: int = 0
    errors: int = 0
    rate_limit_strikes: int = 0
    hard_failures: int = 0
    # Auto-heal tracking
    auto_heal_successes: int = 0
    auto_heal_target: int = 2
    auto_heal_failures: int = 0
    auto_heal_last_check: float = 0.0
    # Consecutive error tracking (Envoy pattern)
    consecutive_errors: int = 0

    def available(self, now: float) -> bool:
        if now < self.blacklist_until:
            return False
        if now < self.limit_until:
            return False
        if now < self.cooldown_until:
            return False
        if (
            self.probation_successes < self.probation_target
            and now < self.next_probe_after
        ):
            return False
        return True

    def status(self, now: float) -> str:
        if now < self.blacklist_until:
            return "BLACKLIST"
        if now < self.limit_until:
            return "COOLDOWN"
        if now < self.cooldown_until:
            return "COOLDOWN"
        if self.probation_successes < self.probation_target:
            return "PROBATION"
        return "OK"

    def health(self, now: float) -> Dict[str, Any]:
        runtime_remaining = (
            int(self.cooldown_until - now) if self.cooldown_until > now else 0
        )
        limit_remaining = int(self.limit_until - now) if self.limit_until > now else 0
        remaining = max(runtime_remaining, limit_remaining)
        blacklist_remaining = (
            int(self.blacklist_until - now) if self.blacklist_until > now else 0
        )
        status = self.status(now)
        reason = None
        reason_origin = None
        until = None
        if status == "BLACKLIST":
            reason = self.blacklist_reason
            reason_origin = "auth"
            until = self.blacklist_until if self.blacklist_until > now else None
        elif limit_remaining > 0:
            reason = self.limit_reason
            reason_origin = "limit"
            until = self.limit_until
        elif runtime_remaining > 0:
            reason = "rate_limited" if self.rate_limit_strikes > 0 else "cooldown"
            reason_origin = "runtime"
            until = self.cooldown_until
        elif status == "PROBATION":
            reason = "probation"
            reason_origin = "probation"
            until = self.next_probe_after if self.next_probe_after > now else None
        return {
            "file": self.record.name,
            "email": self.record.email,
            "status": status,
            "eligible_now": self.available(now),
            "cooldown_seconds": remaining if remaining > 0 else None,
            "blacklist_seconds": blacklist_remaining
            if blacklist_remaining > 0
            else None,
            "blacklist_reason": self.blacklist_reason,
            "limit_reason": self.limit_reason,
            "reason": reason,
            "reason_origin": reason_origin,
            "until": until,
            "probation": status == "PROBATION",
            "probation_successes": self.probation_successes,
            "probation_target": self.probation_target,
            "used": self.used,
            "errors": self.errors,
            "rate_limit_strikes": self.rate_limit_strikes,
            "hard_failures": self.hard_failures,
        }
