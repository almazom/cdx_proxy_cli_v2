from __future__ import annotations

from collections import Counter

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import (
    DEFAULT_BLACKLIST_SECONDS,
    DEFAULT_TRANSIENT_COOLDOWN_SECONDS,
    PROBATION_PROBE_INTERVAL_SECONDS,
    RoundRobinAuthPool,
)
from cdx_proxy_cli_v2.config.settings import (
    DEFAULT_AUTO_RESET_COOLDOWN,
    DEFAULT_AUTO_RESET_STREAK,
)


def _cycle_random_values(pool: RoundRobinAuthPool, values: list[float]) -> None:
    draws = iter(values)
    pool._random.random = lambda: next(draws)


def test_auto_reset_streak_default_is_four() -> None:
    assert DEFAULT_AUTO_RESET_STREAK == 4


def test_auto_reset_cooldown_default_is_120() -> None:
    assert DEFAULT_AUTO_RESET_COOLDOWN == 120


def test_auto_reset_triggers_on_small_pool_by_default(monkeypatch) -> None:
    now = 7000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(consecutive_error_threshold=1)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )

    pool.mark_result("b.json", status=401, error_code="token_invalid")

    reset_count = 0
    for _ in range(4):
        picked = pool.pick()
        assert picked is not None
        assert picked.record.name == "a.json"
        reset_count = pool.maybe_auto_reset_single_key(picked.record.name, now)

    assert reset_count == 1
    snapshot = {item["file"]: item for item in pool.health_snapshot()}
    assert snapshot["b.json"]["status"] == "OK"


def test_auto_reset_uses_ring_buffer_not_global_counter(monkeypatch) -> None:
    now = 7100.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(
        auto_reset_on_single_key=True,
        auto_reset_streak=4,
        consecutive_error_threshold=1,
    )
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
            AuthRecord(
                name="c.json", path="/tmp/c.json", token="tok-c", email="c@example.com"
            ),
        ]
    )

    pool.mark_result("c.json", status=401, error_code="token_invalid")

    assert pool.maybe_auto_reset_single_key("a.json", now) == 0
    assert pool.maybe_auto_reset_single_key("b.json", now) == 0
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0

    snapshot = {item["file"]: item for item in pool.health_snapshot()}
    assert snapshot["c.json"]["status"] == "BLACKLIST"


def test_auto_reset_respects_cooldown(monkeypatch) -> None:
    now = 7200.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(
        auto_reset_on_single_key=True,
        auto_reset_streak=2,
        auto_reset_cooldown=120,
        consecutive_error_threshold=1,
    )
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )

    pool.mark_result("b.json", status=401, error_code="token_invalid")
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0
    assert pool.maybe_auto_reset_single_key("a.json", now) == 1

    pool.mark_result("b.json", status=401, error_code="token_invalid")
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0


def test_auto_reset_returns_zero_when_no_blacklisted_keys(monkeypatch) -> None:
    now = 7300.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(auto_reset_on_single_key=True, auto_reset_streak=4)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )

    assert pool.maybe_auto_reset_single_key("a.json", now) == 0
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0
    assert pool.maybe_auto_reset_single_key("a.json", now) == 0


def test_round_robin_and_cooldown() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )
    pool._random.seed(0)

    first = pool.pick()
    assert first is not None
    pool.mark_cooldown(first.record.name, seconds=60)

    second = pool.pick()
    assert second is not None
    assert second.record.name != first.record.name


def test_pick_can_filter_allowed_names() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )

    picked = pool.pick(allowed_names={"b.json"})

    assert picked is not None
    assert picked.record.name == "b.json"
    assert pool.pick(allowed_names={"missing.json"}) is None


def test_preview_next_pick_can_filter_allowed_names() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )

    preview = pool.preview_next_pick(allowed_names={"b.json"})

    assert preview is not None
    assert preview["file"] == "b.json"
    assert pool.preview_next_pick(allowed_names={"missing.json"}) is None


def test_blacklist_then_probation_then_recovery(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(
        consecutive_error_threshold=1
    )  # Blacklist on first error for test
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

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
    pool = RoundRobinAuthPool(
        consecutive_error_threshold=1
    )  # Blacklist on first error for test
    pool.load(
        [
            AuthRecord(
                name="a.json",
                path="/tmp/a.json",
                token="tok-old",
                email="a@example.com",
            )
        ]
    )

    pool.mark_result("a.json", status=401, error_code="token_expired")
    assert pool.pick() is None

    # Same file name but refreshed token should return to whitelist.
    pool.load(
        [
            AuthRecord(
                name="a.json",
                path="/tmp/a.json",
                token="tok-new",
                email="a@example.com",
            )
        ]
    )
    assert pool.pick() is not None


def test_account_incompatible_400_blacklists_immediately(monkeypatch) -> None:
    now = 2500.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

    picked = pool.pick()
    assert picked is not None

    pool.mark_result("a.json", status=400, error_code="chatgpt_account_incompatible")
    assert pool.pick() is None


def test_prefers_stable_keys_when_available(monkeypatch) -> None:
    now = 3000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
    pool = RoundRobinAuthPool(
        consecutive_error_threshold=1
    )  # Blacklist on first error for test
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )

    # Mark key A as hard-failed; it will become available later via probation.
    pool.mark_result("a.json", status=401, error_code="token_expired")
    now = now + float(DEFAULT_BLACKLIST_SECONDS) + 1.0

    # Key B is stable, so foreground selection should avoid key A.
    picked = pool.pick()
    assert picked is not None
    assert picked.record.name == "b.json"


def test_hard_auth_failures_are_not_force_restored_by_max_ejection() -> None:
    pool = RoundRobinAuthPool(max_ejection_percent=50, consecutive_error_threshold=1)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
            AuthRecord(
                name="c.json", path="/tmp/c.json", token="tok-c", email="c@example.com"
            ),
        ]
    )

    for auth_name in ["a.json", "b.json", "c.json"]:
        pool.mark_result(auth_name, status=401, error_code="token_invalid")

    assert pool.pick() is None
    assert pool.stats()["blacklist"] == 1
    assert pool.stats()["cooldown"] == 2


def test_max_ejection_percent_prevents_blacklist_when_threshold_exceeded(
    monkeypatch,
) -> None:
    now = 3200.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(max_ejection_percent=50, consecutive_error_threshold=1)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )

    pool.mark_result("a.json", status=401, error_code="token_invalid")
    pool.mark_result("b.json", status=401, error_code="token_invalid")

    snapshot = {item["file"]: item for item in pool.health_snapshot()}
    assert snapshot["a.json"]["status"] == "BLACKLIST"
    assert snapshot["b.json"]["status"] == "COOLDOWN"
    assert snapshot["b.json"]["blacklist_seconds"] is None


def test_consecutive_error_threshold_delays_blacklist(monkeypatch) -> None:
    now = 3500.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(consecutive_error_threshold=2)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

    pool.mark_result("a.json", status=403, error_code="forbidden")
    snapshot = pool.health_snapshot()[0]
    assert snapshot["status"] == "COOLDOWN"

    now = now + float(DEFAULT_TRANSIENT_COOLDOWN_SECONDS) + 1.0
    assert pool.pick() is not None

    pool.mark_result("a.json", status=403, error_code="forbidden")
    assert pool.health_snapshot()[0]["status"] == "BLACKLIST"


def test_rate_limited_key_rejoins_rotation_after_cooldown(monkeypatch) -> None:
    now = 4000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )
    pool._random.seed(0)

    first = pool.pick()
    assert first is not None
    pool.mark_result(first.record.name, status=429, cooldown_seconds=5)

    second = pool.pick()
    assert second is not None
    assert second.record.name != first.record.name

    now = now + 6.0
    recovered = pool.pick()
    assert recovered is not None
    assert recovered.record.name == first.record.name


def test_persistently_rate_limited_keys_are_not_force_restored() -> None:
    pool = RoundRobinAuthPool(max_ejection_percent=50)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
            AuthRecord(
                name="c.json", path="/tmp/c.json", token="tok-c", email="c@example.com"
            ),
        ]
    )

    for auth_name in ["a.json", "b.json", "c.json"]:
        for _ in range(5):
            pool.mark_result(auth_name, status=429)

    assert pool.pick() is None
    snapshot = {item["file"]: item for item in pool.health_snapshot()}
    assert snapshot["a.json"]["status"] == "BLACKLIST"
    assert snapshot["b.json"]["status"] == "COOLDOWN"
    assert snapshot["c.json"]["status"] == "COOLDOWN"


def test_weighted_pick_skips_unavailable_auths(monkeypatch) -> None:
    now = 5000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
            AuthRecord(
                name="c.json", path="/tmp/c.json", token="tok-c", email="c@example.com"
            ),
        ]
    )
    pool._random.seed(4)

    first = pool.pick()
    assert first is not None
    assert first.record.name == "a.json"

    pool.mark_result("a.json", status=429, cooldown_seconds=60)
    second = pool.pick()
    assert second is not None
    assert second.record.name in {"b.json", "c.json"}


def test_probation_recovery_returns_key_to_round_robin(monkeypatch) -> None:
    now = 4500.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(consecutive_error_threshold=1)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )
    pool._random.seed(0)

    pool.mark_result("a.json", status=401, error_code="token_invalid")

    now = now + float(DEFAULT_BLACKLIST_SECONDS) + 1.0
    assert pool.pick() is not None
    pool.mark_result("a.json", status=200)

    now = now + float(PROBATION_PROBE_INTERVAL_SECONDS) + 1.0
    pool.mark_result("a.json", status=200)

    picks = [pool.pick(), pool.pick()]
    pick_names = [picked.record.name for picked in picks if picked is not None]
    assert "a.json" in pick_names


def test_reset_ignores_limit_only_cooldown(monkeypatch) -> None:
    now = 5500.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

    pool._states[0].limit_until = now + 300.0
    pool._states[0].limit_reason = "limit_5h"

    assert pool.reset_auth(state="cooldown") == 0
    snapshot = pool.health_snapshot()[0]
    assert snapshot["status"] == "COOLDOWN"
    assert snapshot["reason"] == "limit_5h"


def test_nearly_exhausted_limit_window_temporarily_leaves_rotation(monkeypatch) -> None:
    now = 6100.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

    pool.apply_limit_health(
        {
            "a.json": {
                "five_hour": {
                    "status": "WARN",
                    "used_percent": 89.5,
                    "reset_after_seconds": 120,
                }
            }
        },
        min_remaining_percent=15.0,
    )

    assert pool.pick() is None
    snapshot = pool.health_snapshot()[0]
    assert snapshot["status"] == "COOLDOWN"
    assert snapshot["reason"] == "limit_5h_guardrail"

    now = now + 121.0
    recovered = pool.pick()
    assert recovered is not None
    assert recovered.record.name == "a.json"


def test_non_auth_4xx_does_not_penalize_key(monkeypatch) -> None:
    now = 5000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(consecutive_error_threshold=2)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

    pool.mark_result("a.json", status=405)
    snapshot = pool.health_snapshot()[0]

    assert snapshot["status"] == "OK"
    assert snapshot["errors"] == 0
    assert snapshot["hard_failures"] == 0


def test_non_auth_4xx_resets_hard_failure_streak(monkeypatch) -> None:
    now = 5500.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(consecutive_error_threshold=2)
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

    pool.mark_result("a.json", status=403, error_code="forbidden")
    assert pool.health_snapshot()[0]["status"] == "COOLDOWN"

    now = now + float(DEFAULT_TRANSIENT_COOLDOWN_SECONDS) + 1.0
    pool.mark_result("a.json", status=405)
    pool.mark_result("a.json", status=403, error_code="forbidden")

    assert pool.health_snapshot()[0]["status"] == "COOLDOWN"


def test_weighted_pick_prefers_higher_capacity_keys() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )
    pool._states[0].remaining_capacity_weight = 0.9
    pool._states[1].remaining_capacity_weight = 0.1
    _cycle_random_values(pool, [step / 100 for step in range(100)])

    counts = Counter()
    for _ in range(100):
        picked = pool.pick()
        assert picked is not None
        counts[picked.record.name] += 1

    assert counts["a.json"] >= 70


def test_weighted_pick_falls_back_to_uniform_when_no_limit_data() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )
    _cycle_random_values(pool, [step / 100 for step in range(100)])

    counts = Counter()
    for _ in range(100):
        picked = pool.pick()
        assert picked is not None
        counts[picked.record.name] += 1

    assert counts["a.json"] >= 30
    assert counts["b.json"] >= 30


def test_weighted_pick_with_all_keys_equal_is_uniform() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            ),
            AuthRecord(
                name="b.json", path="/tmp/b.json", token="tok-b", email="b@example.com"
            ),
        ]
    )
    pool._states[0].remaining_capacity_weight = 0.5
    pool._states[1].remaining_capacity_weight = 0.5
    _cycle_random_values(pool, [step / 100 for step in range(100)])

    counts = Counter()
    for _ in range(100):
        picked = pool.pick()
        assert picked is not None
        counts[picked.record.name] += 1

    assert counts["a.json"] >= 30
    assert counts["b.json"] >= 30


def test_weighted_pick_respects_stable_filter() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="stable.json",
                path="/tmp/stable.json",
                token="tok-stable",
                email="stable@example.com",
            ),
            AuthRecord(
                name="unstable.json",
                path="/tmp/unstable.json",
                token="tok-unstable",
                email="unstable@example.com",
            ),
        ]
    )
    pool._states[0].remaining_capacity_weight = 0.1
    pool._states[1].remaining_capacity_weight = 0.9
    pool._states[1].hard_failures = 1
    _cycle_random_values(pool, [step / 100 for step in range(100)])

    for _ in range(20):
        picked = pool.pick()
        assert picked is not None
        assert picked.record.name == "stable.json"


def test_apply_limit_health_sets_weight_from_used_percent() -> None:
    pool = RoundRobinAuthPool()
    pool.load(
        [
            AuthRecord(
                name="a.json", path="/tmp/a.json", token="tok-a", email="a@example.com"
            )
        ]
    )

    pool.apply_limit_health(
        {
            "a.json": {
                "five_hour": {
                    "status": "OK",
                    "used_percent": 25.0,
                    "reset_after_seconds": 300,
                }
            }
        },
        min_remaining_percent=10.0,
    )

    assert pool._states[0].remaining_capacity_weight == 0.75
