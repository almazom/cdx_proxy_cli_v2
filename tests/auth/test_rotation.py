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

    pool = RoundRobinAuthPool(consecutive_error_threshold=1)  # Blacklist on first error for test
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
    pool = RoundRobinAuthPool(consecutive_error_threshold=1)  # Blacklist on first error for test
    pool.load([AuthRecord(name="a.json", path="/tmp/a.json", token="tok-old", email="a@example.com")])

    pool.mark_result("a.json", status=401, error_code="token_expired")
    assert pool.pick() is None

    # Same file name but refreshed token should return to whitelist.
    pool.load([AuthRecord(name="a.json", path="/tmp/a.json", token="tok-new", email="a@example.com")])
    assert pool.pick() is not None


def test_account_incompatible_400_blacklists_immediately(monkeypatch) -> None:
    now = 2500.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
    pool = RoundRobinAuthPool()
    pool.load([AuthRecord(name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com")])

    picked = pool.pick()
    assert picked is not None

    pool.mark_result("a.json", status=400, error_code="chatgpt_account_incompatible")
    assert pool.pick() is None


def test_prefers_stable_keys_when_available(monkeypatch) -> None:
    now = 3000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
    pool = RoundRobinAuthPool(consecutive_error_threshold=1)  # Blacklist on first error for test
    pool.load(
        [
            AuthRecord(name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"),
            AuthRecord(name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"),
        ]
    )

    # Mark key A as hard-failed; it will become available later via probation.
    pool.mark_result("a.json", status=401, error_code="token_expired")
    now = now + float(DEFAULT_BLACKLIST_SECONDS) + 1.0

    # Key B is stable, so foreground selection should avoid key A.
    picked = pool.pick()
    assert picked is not None
    assert picked.record.name == "b.json"


def test_max_ejection_force_restore_makes_key_immediately_available() -> None:
    pool = RoundRobinAuthPool(max_ejection_percent=50, consecutive_error_threshold=1)
    pool.load(
        [
            AuthRecord(name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"),
            AuthRecord(name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"),
            AuthRecord(name="c.json", path="/tmp/c.json", token="tok-c", email="c@example.com"),
        ]
    )

    for auth_name in ["a.json", "b.json", "c.json"]:
        pool.mark_result(auth_name, status=401, error_code="token_invalid")

    picked = pool.pick()
    assert picked is not None
    assert pool.stats()["ok"] >= 1
