from __future__ import annotations

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import (
    DEFAULT_BLACKLIST_SECONDS,
    PROBATION_PROBE_INTERVAL_SECONDS,
    RoundRobinAuthPool,
)


def test_round_robin_and_cooldown() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"),
            AuthRecord(name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"),
        ]
    )

    first = pool.pick()
    assert first is not None
    pool.mark_cooldown(first.record.name, seconds=60)

    second = pool.pick()
    assert second is not None
    assert second.record.name != first.record.name


def test_blacklist_then_probation_then_recovery(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool()
    pool.load([AuthRecord(name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com")])

    picked = pool.pick()
    assert picked is not None
    assert picked.record.name == "a.json"

    pool.mark_result("a.json", status=401, error_code="token_expired")
    assert pool.pick() is None

    now = now + float(DEFAULT_BLACKLIST_SECONDS) + 1.0
    probe1 = pool.pick()
    assert probe1 is not None
    assert probe1.record.name == "a.json"
    pool.mark_result("a.json", status=200)

    # Still probation: immediate pick blocked by probe interval.
    assert pool.pick() is None
    now = now + float(PROBATION_PROBE_INTERVAL_SECONDS) + 1.0
    probe2 = pool.pick()
    assert probe2 is not None
    pool.mark_result("a.json", status=200)

    # Back to whitelist: no waiting needed.
    assert pool.pick() is not None


def test_token_change_resets_blacklist_state(monkeypatch) -> None:
    now = 2000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
    pool = RoundRobinAuthPool()
    pool.load([AuthRecord(name="a.json", path="/tmp/a.json", token="tok-old", email="a@example.com")])

    pool.mark_result("a.json", status=401, error_code="token_expired")
    assert pool.pick() is None

    # Same file name but refreshed token should return to whitelist.
    pool.load([AuthRecord(name="a.json", path="/tmp/a.json", token="tok-new", email="a@example.com")])
    assert pool.pick() is not None
