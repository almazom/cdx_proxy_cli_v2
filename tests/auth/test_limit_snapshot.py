from __future__ import annotations

from pathlib import Path

from cdx_proxy_cli_v2.auth.limit_snapshot import (
    BOOT_SNAPSHOT_FILENAME,
    load_boot_snapshot,
    write_boot_snapshot,
)
from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.auth.rotation import RoundRobinAuthPool


def test_boot_snapshot_written_and_loaded(tmp_path: Path) -> None:
    now = 1_000.0
    path = write_boot_snapshot(
        str(tmp_path),
        [
            {
                "file": "a.json",
                "cooldown_until": now + 30,
                "limit_until": now + 60,
                "limit_reason": "limit_low",
                "blacklist_until": now + 90,
                "blacklist_reason": "rate_limited_persistent",
                "rate_limit_strikes": 4,
                "hard_failures": 2,
                "consecutive_errors": 3,
                "probation_successes": 0,
                "probation_target": 2,
            }
        ],
    )

    assert path == tmp_path / BOOT_SNAPSHOT_FILENAME
    assert path.exists()

    loaded = load_boot_snapshot(str(tmp_path), now)

    assert loaded == {
        "a.json": {
            "name": "a.json",
            "cooldown_until": now + 30,
            "limit_until": now + 60,
            "limit_reason": "limit_low",
            "blacklist_until": now + 90,
            "blacklist_reason": "rate_limited_persistent",
            "rate_limit_strikes": 4,
            "hard_failures": 2,
            "consecutive_errors": 3,
            "probation_successes": 0,
            "probation_target": 2,
        }
    }


def test_boot_snapshot_skips_expired_entries(tmp_path: Path) -> None:
    now = 2_000.0
    write_boot_snapshot(
        str(tmp_path),
        [
            {
                "file": "expired.json",
                "cooldown_until": now - 30,
                "limit_until": now - 20,
                "blacklist_until": now - 10,
            },
            {
                "file": "active.json",
                "cooldown_until": now - 30,
                "limit_until": now + 20,
                "blacklist_until": now - 10,
            },
        ],
    )

    loaded = load_boot_snapshot(str(tmp_path), now)

    assert set(loaded) == {"active.json"}


def test_boot_snapshot_deleted_after_load(tmp_path: Path) -> None:
    now = 3_000.0
    path = write_boot_snapshot(
        str(tmp_path),
        [{"file": "a.json", "cooldown_until": now + 30}],
    )

    load_boot_snapshot(str(tmp_path), now)

    assert not path.exists()


def test_boot_snapshot_missing_is_not_an_error(tmp_path: Path) -> None:
    assert load_boot_snapshot(str(tmp_path), 4_000.0) == {}


def test_boot_snapshot_invalid_json_is_not_an_error(tmp_path: Path) -> None:
    path = tmp_path / BOOT_SNAPSHOT_FILENAME
    path.write_text("{bad json", encoding="utf-8")

    assert load_boot_snapshot(str(tmp_path), 5_000.0) == {}


def test_pool_load_from_snapshot_restores_state(
    monkeypatch, tmp_path: Path
) -> None:
    now = 6_000.0
    monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)

    pool = RoundRobinAuthPool(consecutive_error_threshold=1)
    records = [
        AuthRecord(
            name="a.json",
            path="/tmp/a.json",
            token="tok-a",
            email="a@example.com",
        )
    ]
    pool.load(records)
    pool.mark_result("a.json", status=401, error_code="token_invalid")
    write_boot_snapshot(str(tmp_path), pool.health_snapshot())

    restored_pool = RoundRobinAuthPool(consecutive_error_threshold=1)
    restored_pool.load(records)
    restored = restored_pool.load_from_snapshot(
        load_boot_snapshot(str(tmp_path), now),
        now,
    )

    assert restored == 1
    assert restored_pool.pick() is None
    snapshot = restored_pool.health_snapshot()[0]
    assert snapshot["status"] == "BLACKLIST"
    assert snapshot["blacklist_reason"] == "token_invalid"
