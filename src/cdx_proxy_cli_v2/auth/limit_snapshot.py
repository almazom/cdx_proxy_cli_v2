from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

BOOT_SNAPSHOT_FILENAME = "rr_proxy_v2_boot_snapshot.json"
_SNAPSHOT_FIELDS = (
    "cooldown_until",
    "limit_until",
    "limit_reason",
    "blacklist_until",
    "blacklist_reason",
    "rate_limit_strikes",
    "hard_failures",
    "consecutive_errors",
    "probation_successes",
    "probation_target",
)


def _snapshot_path(auth_dir: str) -> Path:
    return Path(auth_dir).expanduser() / BOOT_SNAPSHOT_FILENAME


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def write_boot_snapshot(auth_dir: str, states: list[dict]) -> Path:
    path = _snapshot_path(auth_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    compact_states: list[dict] = []
    for state in states:
        if not isinstance(state, dict):
            continue
        name = str(state.get("name") or state.get("file") or "").strip()
        if not name:
            continue
        compact = {"name": name}
        for field in _SNAPSHOT_FIELDS:
            compact[field] = state.get(field)
        compact_states.append(compact)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=".",
        dir=str(path.parent),
        delete=False,
        encoding="utf-8",
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(compact_states, handle, separators=(",", ":"), ensure_ascii=True)
        handle.write("\n")
    try:
        temp_path.chmod(0o600)
    except OSError:
        pass
    temp_path.replace(path)
    return path


def load_boot_snapshot(auth_dir: str, now: float) -> dict[str, dict]:
    path = _snapshot_path(auth_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}

    if not isinstance(raw, list):
        return {}

    restored: dict[str, dict] = {}
    expired = 0
    for item in raw:
        if not isinstance(item, dict):
            expired += 1
            continue
        name = str(item.get("name") or item.get("file") or "").strip()
        if not name:
            expired += 1
            continue
        cooldown_until = _as_float(item.get("cooldown_until"))
        limit_until = _as_float(item.get("limit_until"))
        blacklist_until = _as_float(item.get("blacklist_until"))
        if (
            cooldown_until < now
            and limit_until < now
            and blacklist_until < now
        ):
            expired += 1
            continue
        entry = dict(item)
        entry["name"] = name
        entry["cooldown_until"] = cooldown_until
        entry["limit_until"] = limit_until
        entry["blacklist_until"] = blacklist_until
        restored[name] = entry

    try:
        path.unlink()
    except OSError:
        pass
    logger.info(
        "Restored %s keys from boot snapshot, %s expired entries skipped",
        len(restored),
        expired,
    )
    return restored
