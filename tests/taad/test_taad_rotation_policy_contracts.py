from __future__ import annotations

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import (
    DEFAULT_BLACKLIST_SECONDS,
    PROBATION_PROBE_INTERVAL_SECONDS,
    RoundRobinAuthPool,
)


def test_taad_401_blacklists_then_reenters_via_probation(monkeypatch) -> None:
    """TaaD Safety: hard auth failures are ejected and only rejoin after probation."""
    now = 1000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool()
    pool.load([AuthRecord(name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com")])

    picked = pool.pick()
    assert picked is not None
    pool.mark_result("a.json", status=401, error_code="token_expired")

    assert pool.pick() is None

    now = now + float(DEFAULT_BLACKLIST_SECONDS) + 1.0
    probe1 = pool.pick()
    assert probe1 is not None
    pool.mark_result("a.json", status=200)

    assert pool.pick() is None
    now = now + float(PROBATION_PROBE_INTERVAL_SECONDS) + 1.0
    probe2 = pool.pick()
    assert probe2 is not None
    pool.mark_result("a.json", status=200)

    assert pool.pick() is not None


def test_taad_429_cooldown_rotates_to_next_key() -> None:
    """TaaD Functional Fit: rate-limited key is cooled down and rotation continues."""
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"),
            AuthRecord(name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"),
        ]
    )
    first = pool.pick()
    assert first is not None
    pool.mark_result(first.record.name, status=429)

    second = pool.pick()
    assert second is not None
    assert second.record.name != first.record.name

