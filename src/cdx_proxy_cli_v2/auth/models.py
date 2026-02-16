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
    blacklist_until: float = 0.0
    blacklist_reason: Optional[str] = None
    probation_successes: int = 2
    probation_target: int = 2
    next_probe_after: float = 0.0
    used: int = 0
    errors: int = 0
    rate_limit_strikes: int = 0
    hard_failures: int = 0

    def available(self, now: float) -> bool:
        if now < self.blacklist_until:
            return False
        if now < self.cooldown_until:
            return False
        if self.probation_successes < self.probation_target and now < self.next_probe_after:
            return False
        return True

    def status(self, now: float) -> str:
        if now < self.blacklist_until:
            return "BLACKLIST"
        if now < self.cooldown_until:
            return "COOLDOWN"
        if self.probation_successes < self.probation_target:
            if now < self.next_probe_after:
                return "BLACKLIST"
            return "PROBATION"
        return "OK"

    def health(self, now: float) -> Dict[str, Any]:
        remaining = int(self.cooldown_until - now) if self.cooldown_until > now else 0
        blacklist_remaining = int(self.blacklist_until - now) if self.blacklist_until > now else 0
        status = self.status(now)
        return {
            "file": self.record.name,
            "email": self.record.email,
            "status": status,
            "cooldown_seconds": remaining if remaining > 0 else None,
            "blacklist_seconds": blacklist_remaining if blacklist_remaining > 0 else None,
            "blacklist_reason": self.blacklist_reason,
            "probation": status == "PROBATION",
            "probation_successes": self.probation_successes,
            "probation_target": self.probation_target,
            "used": self.used,
            "errors": self.errors,
            "rate_limit_strikes": self.rate_limit_strikes,
            "hard_failures": self.hard_failures,
        }
