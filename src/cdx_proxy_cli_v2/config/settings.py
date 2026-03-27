from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

DEFAULT_AUTH_DIR = "~/.codex/_auths"
DEFAULT_ENV_FILE = ".env"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_UPSTREAM = "https://chatgpt.com/backend-api"
DEFAULT_TRACE_MAX = 500
DEFAULT_REQUEST_TIMEOUT = 45
DEFAULT_COMPACT_TIMEOUT = 120
DEFAULT_LIMIT_MIN_REMAINING_PERCENT = 11.0
DEFAULT_AUTO_RESET_STREAK = 12
DEFAULT_AUTO_RESET_COOLDOWN = 5 * 60
DEFAULT_MAX_IN_FLIGHT_REQUESTS = 0
DEFAULT_MAX_PENDING_REQUESTS = 0
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_TOP = "12%"
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_RIGHT = "2%"
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_WIDTH = "40%"
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_HEIGHT = "35%"
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_CLOSE_ON_EXIT = False
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_PINNED = True
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_NAME = ""
DEFAULT_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX = "cdx:"
DEFAULT_CODEX_WP_ZELLIJ_PAIR_LAYOUT = "top-right-double"
DEFAULT_CODEX_WP_ZELLIJ_PAIR_TOP = "12%"
DEFAULT_CODEX_WP_ZELLIJ_PAIR_RIGHT = "2%"
DEFAULT_CODEX_WP_ZELLIJ_PAIR_WIDTH = "40%"
DEFAULT_CODEX_WP_ZELLIJ_PAIR_HEIGHT = "72%"
DEFAULT_CODEX_WP_ZELLIJ_PAIR_GAP = "1"
DEFAULT_CODEX_WP_ZELLIJ_AUTO_NAME = True
DEFAULT_CODEX_WP_ZELLIJ_TITLE_MAX_WORDS = 3
DEFAULT_CODEX_WP_ZELLIJ_TITLE_CASE = "title"
DEFAULT_CODEX_WP_ZELLIJ_TITLE_FALLBACK = "Codex Task"

# Auto-heal blacklist configuration defaults (Envoy-inspired)
DEFAULT_AUTO_HEAL_INTERVAL = 60  # seconds between health checks
DEFAULT_AUTO_HEAL_SUCCESS_TARGET = 2  # successes needed to restore
DEFAULT_AUTO_HEAL_MAX_ATTEMPTS = 3  # failures before penalty
DEFAULT_MAX_EJECTION_PERCENT = 50  # Max % of keys that can be blacklisted
DEFAULT_CONSECUTIVE_ERROR_THRESHOLD = 3  # Errors before blacklist

ENV_AUTH_DIR = "CLIPROXY_AUTH_DIR"
ENV_ENV_FILE = "CLIPROXY_ENV_FILE"
ENV_HOST = "CLIPROXY_HOST"
ENV_PORT = "CLIPROXY_PORT"
ENV_UPSTREAM = "CLIPROXY_UPSTREAM"
ENV_MANAGEMENT_KEY = "CLIPROXY_MANAGEMENT_KEY"
ENV_ALLOW_NON_LOOPBACK = "CLIPROXY_ALLOW_NON_LOOPBACK"
ENV_TRACE_MAX = "CLIPROXY_TRACE_MAX"
ENV_REQUEST_TIMEOUT = "CLIPROXY_REQUEST_TIMEOUT"
ENV_COMPACT_TIMEOUT = "CLIPROXY_COMPACT_TIMEOUT"
ENV_LIMIT_MIN_REMAINING_PERCENT = "CLIPROXY_LIMIT_MIN_REMAINING_PERCENT"
ENV_MAX_IN_FLIGHT_REQUESTS = "CLIPROXY_MAX_IN_FLIGHT_REQUESTS"
ENV_MAX_PENDING_REQUESTS = "CLIPROXY_MAX_PENDING_REQUESTS"
ENV_AUTO_RESET_ON_SINGLE_KEY = "CLIPROXY_AUTO_RESET_ON_SINGLE_KEY"
ENV_AUTO_RESET_STREAK = "CLIPROXY_AUTO_RESET_STREAK"
ENV_AUTO_RESET_COOLDOWN = "CLIPROXY_AUTO_RESET_COOLDOWN"
# Auto-heal configuration
ENV_AUTO_HEAL_INTERVAL = "CLIPROXY_AUTO_HEAL_INTERVAL"
ENV_AUTO_HEAL_SUCCESS_TARGET = "CLIPROXY_AUTO_HEAL_SUCCESS_TARGET"
ENV_AUTO_HEAL_MAX_ATTEMPTS = "CLIPROXY_AUTO_HEAL_MAX_ATTEMPTS"
ENV_MAX_EJECTION_PERCENT = "CLIPROXY_MAX_EJECTION_PERCENT"
ENV_CONSECUTIVE_ERROR_THRESHOLD = "CLIPROXY_CONSECUTIVE_ERROR_THRESHOLD"
ENV_CODEX_WP_ZELLIJ_FLOAT_TOP = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_TOP"
ENV_CODEX_WP_ZELLIJ_FLOAT_RIGHT = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_RIGHT"
ENV_CODEX_WP_ZELLIJ_FLOAT_WIDTH = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_WIDTH"
ENV_CODEX_WP_ZELLIJ_FLOAT_HEIGHT = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_HEIGHT"
ENV_CODEX_WP_ZELLIJ_FLOAT_CLOSE_ON_EXIT = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_CLOSE_ON_EXIT"
ENV_CODEX_WP_ZELLIJ_FLOAT_PINNED = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_PINNED"
ENV_CODEX_WP_ZELLIJ_FLOAT_NAME = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_NAME"
ENV_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX = "CLIPROXY_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX"
ENV_CODEX_WP_ZELLIJ_PAIR_LAYOUT = "CLIPROXY_CODEX_WP_ZELLIJ_PAIR_LAYOUT"
ENV_CODEX_WP_ZELLIJ_PAIR_TOP = "CLIPROXY_CODEX_WP_ZELLIJ_PAIR_TOP"
ENV_CODEX_WP_ZELLIJ_PAIR_RIGHT = "CLIPROXY_CODEX_WP_ZELLIJ_PAIR_RIGHT"
ENV_CODEX_WP_ZELLIJ_PAIR_WIDTH = "CLIPROXY_CODEX_WP_ZELLIJ_PAIR_WIDTH"
ENV_CODEX_WP_ZELLIJ_PAIR_HEIGHT = "CLIPROXY_CODEX_WP_ZELLIJ_PAIR_HEIGHT"
ENV_CODEX_WP_ZELLIJ_PAIR_GAP = "CLIPROXY_CODEX_WP_ZELLIJ_PAIR_GAP"
ENV_CODEX_WP_ZELLIJ_AUTO_NAME = "CLIPROXY_CODEX_WP_ZELLIJ_AUTO_NAME"
ENV_CODEX_WP_ZELLIJ_TITLE_MAX_WORDS = "CLIPROXY_CODEX_WP_ZELLIJ_TITLE_MAX_WORDS"
ENV_CODEX_WP_ZELLIJ_TITLE_CASE = "CLIPROXY_CODEX_WP_ZELLIJ_TITLE_CASE"
ENV_CODEX_WP_ZELLIJ_TITLE_FALLBACK = "CLIPROXY_CODEX_WP_ZELLIJ_TITLE_FALLBACK"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_CHATGPT_BACKEND_HOSTS = {"chatgpt.com", "chat.openai.com"}
_CHATGPT_BACKEND_PATH = "/backend-api"


def resolve_path(path: str) -> Path:
    return Path(os.path.expanduser(path))


def env_file_path(auth_dir: str, env_file: Optional[str] = None) -> Path:
    explicit = str(env_file or "").strip()
    if explicit:
        return resolve_path(explicit)
    return resolve_path(auth_dir) / DEFAULT_ENV_FILE


def scoped_env_file_path(
    auth_dir: str, env_file: Optional[str] = None
) -> Optional[Path]:
    explicit = str(env_file or "").strip()
    if not explicit:
        return None
    resolved_auth_dir = resolve_path(auth_dir).resolve()
    resolved_env_file = resolve_path(explicit).resolve()
    try:
        resolved_env_file.relative_to(resolved_auth_dir)
    except ValueError:
        return None
    return resolved_env_file


def _resolve_inherited_env_file_path(
    auth_dir: str,
    env_file: Optional[str],
    *,
    require_auth_dir_scope: bool,
) -> Optional[Path]:
    if require_auth_dir_scope:
        return scoped_env_file_path(auth_dir, env_file)
    explicit = str(env_file or "").strip()
    if not explicit:
        return None
    return resolve_path(explicit)


def parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in _TRUE_VALUES


def parse_port(value: Optional[str], default: int = 0) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if not (0 <= parsed <= 65535):
        return default
    return parsed


def parse_positive_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def parse_percentage_float(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if parsed < 0:
        return default
    return min(100.0, parsed)


def normalize_upstream(value: Optional[str], default: str = DEFAULT_UPSTREAM) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").strip().lower()
    if host in _CHATGPT_BACKEND_HOSTS and (parsed.path or "") in {"", "/"}:
        parsed = parsed._replace(path=_CHATGPT_BACKEND_PATH)
        return urlunsplit(parsed)
    return raw


def ensure_private_file(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        return


def ensure_env_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch(mode=0o600, exist_ok=True)
    ensure_private_file(path)


def load_env_file(path: Path) -> Dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return {}
    data: Dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            data[key] = value
    return data


def load_codex_wp_defaults(
    *,
    auth_dir: Optional[str] = None,
    env_file: Optional[str] = None,
) -> Dict[str, object]:
    initial_auth_dir = auth_dir or os.environ.get(ENV_AUTH_DIR) or DEFAULT_AUTH_DIR
    auth_dir_path = resolve_path(initial_auth_dir)
    raw_inherited_env_file = (
        env_file
        if env_file is not None
        else (None if auth_dir is not None else os.environ.get(ENV_ENV_FILE))
    )
    inherited_env_file: Optional[Path]
    if env_file is not None:
        inherited_env_file = resolve_path(env_file)
    elif auth_dir is not None or os.environ.get(ENV_AUTH_DIR):
        inherited_env_file = _resolve_inherited_env_file_path(
            str(auth_dir_path),
            raw_inherited_env_file,
            require_auth_dir_scope=True,
        )
    else:
        inherited_env_file = _resolve_inherited_env_file_path(
            str(auth_dir_path),
            raw_inherited_env_file,
            require_auth_dir_scope=False,
        )
    path = inherited_env_file or env_file_path(str(auth_dir_path))
    merged = load_env_file(path)
    merged.update(os.environ)

    def resolve_text(env_key: str, default: str) -> str:
        value = str(merged.get(env_key) or "").strip()
        return value or default

    return {
        "zellij_float_top": resolve_text(
            ENV_CODEX_WP_ZELLIJ_FLOAT_TOP,
            DEFAULT_CODEX_WP_ZELLIJ_FLOAT_TOP,
        ),
        "zellij_float_right": resolve_text(
            ENV_CODEX_WP_ZELLIJ_FLOAT_RIGHT,
            DEFAULT_CODEX_WP_ZELLIJ_FLOAT_RIGHT,
        ),
        "zellij_float_width": resolve_text(
            ENV_CODEX_WP_ZELLIJ_FLOAT_WIDTH,
            DEFAULT_CODEX_WP_ZELLIJ_FLOAT_WIDTH,
        ),
        "zellij_float_height": resolve_text(
            ENV_CODEX_WP_ZELLIJ_FLOAT_HEIGHT,
            DEFAULT_CODEX_WP_ZELLIJ_FLOAT_HEIGHT,
        ),
        "zellij_float_close_on_exit": parse_bool(
            merged.get(ENV_CODEX_WP_ZELLIJ_FLOAT_CLOSE_ON_EXIT),
            default=DEFAULT_CODEX_WP_ZELLIJ_FLOAT_CLOSE_ON_EXIT,
        ),
        "zellij_float_pinned": parse_bool(
            merged.get(ENV_CODEX_WP_ZELLIJ_FLOAT_PINNED),
            default=DEFAULT_CODEX_WP_ZELLIJ_FLOAT_PINNED,
        ),
        "zellij_float_name": resolve_text(
            ENV_CODEX_WP_ZELLIJ_FLOAT_NAME,
            DEFAULT_CODEX_WP_ZELLIJ_FLOAT_NAME,
        ),
        "zellij_float_title_prefix": resolve_text(
            ENV_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX,
            DEFAULT_CODEX_WP_ZELLIJ_FLOAT_TITLE_PREFIX,
        ),
        "zellij_pair_layout": resolve_text(
            ENV_CODEX_WP_ZELLIJ_PAIR_LAYOUT,
            DEFAULT_CODEX_WP_ZELLIJ_PAIR_LAYOUT,
        ),
        "zellij_pair_top": resolve_text(
            ENV_CODEX_WP_ZELLIJ_PAIR_TOP,
            DEFAULT_CODEX_WP_ZELLIJ_PAIR_TOP,
        ),
        "zellij_pair_right": resolve_text(
            ENV_CODEX_WP_ZELLIJ_PAIR_RIGHT,
            DEFAULT_CODEX_WP_ZELLIJ_PAIR_RIGHT,
        ),
        "zellij_pair_width": resolve_text(
            ENV_CODEX_WP_ZELLIJ_PAIR_WIDTH,
            DEFAULT_CODEX_WP_ZELLIJ_PAIR_WIDTH,
        ),
        "zellij_pair_height": resolve_text(
            ENV_CODEX_WP_ZELLIJ_PAIR_HEIGHT,
            DEFAULT_CODEX_WP_ZELLIJ_PAIR_HEIGHT,
        ),
        "zellij_pair_gap": resolve_text(
            ENV_CODEX_WP_ZELLIJ_PAIR_GAP,
            DEFAULT_CODEX_WP_ZELLIJ_PAIR_GAP,
        ),
        "zellij_auto_name": parse_bool(
            merged.get(ENV_CODEX_WP_ZELLIJ_AUTO_NAME),
            default=DEFAULT_CODEX_WP_ZELLIJ_AUTO_NAME,
        ),
        "zellij_title_max_words": parse_positive_int(
            merged.get(ENV_CODEX_WP_ZELLIJ_TITLE_MAX_WORDS),
            default=DEFAULT_CODEX_WP_ZELLIJ_TITLE_MAX_WORDS,
        ),
        "zellij_title_case": resolve_text(
            ENV_CODEX_WP_ZELLIJ_TITLE_CASE,
            DEFAULT_CODEX_WP_ZELLIJ_TITLE_CASE,
        ),
        "zellij_title_fallback": resolve_text(
            ENV_CODEX_WP_ZELLIJ_TITLE_FALLBACK,
            DEFAULT_CODEX_WP_ZELLIJ_TITLE_FALLBACK,
        ),
    }


def _write_env_file(path: Path, values: Dict[str, str]) -> None:
    lines = [f"{key}={values[key]}" for key in sorted(values.keys())]
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    ensure_private_file(path)


def upsert_env_values(path: Path, updates: Dict[str, str]) -> bool:
    ensure_env_file(path)
    values = load_env_file(path)
    changed = False
    for key, value in updates.items():
        if values.get(key) != value:
            values[key] = value
            changed = True
    if changed:
        _write_env_file(path, values)
    return changed


def remove_env_keys(path: Path, keys: set[str]) -> bool:
    ensure_env_file(path)
    values = load_env_file(path)
    changed = False
    for key in keys:
        if key in values:
            del values[key]
            changed = True
    if changed:
        _write_env_file(path, values)
    return changed


@dataclass(frozen=True)
class Settings:
    auth_dir: str
    host: str
    port: int
    upstream: str
    management_key: Optional[str]
    allow_non_loopback: bool
    trace_max: int
    request_timeout: int
    compact_timeout: int
    limit_min_remaining_percent: float = DEFAULT_LIMIT_MIN_REMAINING_PERCENT
    env_file: Optional[str] = None
    max_in_flight_requests: int = DEFAULT_MAX_IN_FLIGHT_REQUESTS
    max_pending_requests: int = DEFAULT_MAX_PENDING_REQUESTS
    auto_reset_on_single_key: bool = False
    auto_reset_streak: int = DEFAULT_AUTO_RESET_STREAK
    auto_reset_cooldown: int = DEFAULT_AUTO_RESET_COOLDOWN
    # Auto-heal configuration (Envoy-inspired)
    auto_heal_interval: int = DEFAULT_AUTO_HEAL_INTERVAL
    auto_heal_success_target: int = DEFAULT_AUTO_HEAL_SUCCESS_TARGET
    auto_heal_max_attempts: int = DEFAULT_AUTO_HEAL_MAX_ATTEMPTS
    max_ejection_percent: int = DEFAULT_MAX_EJECTION_PERCENT
    consecutive_error_threshold: int = DEFAULT_CONSECUTIVE_ERROR_THRESHOLD

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def env_path(self) -> Path:
        return env_file_path(self.auth_dir, self.env_file)

    def with_port(self, port: int) -> "Settings":
        return replace(self, port=port)

    def with_management_key(self, key: str) -> "Settings":
        return replace(self, management_key=key)


def build_settings(
    *,
    auth_dir: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    upstream: Optional[str] = None,
    management_key: Optional[str] = None,
    allow_non_loopback: Optional[bool] = None,
    trace_max: Optional[int] = None,
    request_timeout: Optional[int] = None,
    compact_timeout: Optional[int] = None,
    limit_min_remaining_percent: Optional[float] = None,
    max_in_flight_requests: Optional[int] = None,
    max_pending_requests: Optional[int] = None,
    auto_reset_on_single_key: Optional[bool] = None,
    auto_reset_streak: Optional[int] = None,
    auto_reset_cooldown: Optional[int] = None,
    auto_heal_interval: Optional[int] = None,
    auto_heal_success_target: Optional[int] = None,
    auto_heal_max_attempts: Optional[int] = None,
    max_ejection_percent: Optional[int] = None,
    consecutive_error_threshold: Optional[int] = None,
) -> Settings:
    initial_auth_dir = auth_dir or os.environ.get(ENV_AUTH_DIR) or DEFAULT_AUTH_DIR
    auth_dir_path = resolve_path(initial_auth_dir)
    raw_inherited_env_file = (
        None if auth_dir is not None else os.environ.get(ENV_ENV_FILE)
    )
    if auth_dir is not None:
        inherited_env_file = None
    elif os.environ.get(ENV_AUTH_DIR):
        inherited_env_file = _resolve_inherited_env_file_path(
            str(auth_dir_path),
            raw_inherited_env_file,
            require_auth_dir_scope=True,
        )
    else:
        inherited_env_file = _resolve_inherited_env_file_path(
            str(auth_dir_path),
            raw_inherited_env_file,
            require_auth_dir_scope=False,
        )
    env_path = inherited_env_file or env_file_path(str(auth_dir_path))
    file_env = load_env_file(env_path)
    merged = dict(file_env)
    merged.update(os.environ)

    # The auth-dir-scoped .env can supply runtime defaults, but it must not
    # redirect startup to a different auth dir.
    resolved_auth_dir = str(auth_dir_path)
    resolved_env_path = (
        env_file_path(resolved_auth_dir) if auth_dir is not None else env_path
    )
    resolved_host = (
        host or merged.get(ENV_HOST) or DEFAULT_HOST
    ).strip() or DEFAULT_HOST

    def resolve_numeric_setting(
        *,
        cli_value: Optional[int],
        env_key: str,
        default: int,
        env_parser: Callable[[Optional[str], int], int],
        min_cli_value: int,
    ) -> int:
        if cli_value is None:
            return env_parser(merged.get(env_key), default)
        return max(min_cli_value, int(cli_value))

    resolved_port = resolve_numeric_setting(
        cli_value=port,
        env_key=ENV_PORT,
        default=0,
        env_parser=parse_port,
        min_cli_value=0,
    )
    if not (0 <= resolved_port <= 65535):
        raise ValueError("port must be between 0 and 65535")

    resolved_upstream = normalize_upstream(
        upstream or merged.get(ENV_UPSTREAM) or DEFAULT_UPSTREAM,
        default=DEFAULT_UPSTREAM,
    )
    raw_key = (
        management_key if management_key is not None else merged.get(ENV_MANAGEMENT_KEY)
    )
    # Handle both Python None and string "None" from env files
    key_str = str(raw_key).strip()
    resolved_key = key_str if key_str and key_str.lower() != "none" else None

    if allow_non_loopback is None:
        resolved_allow_non_loopback = parse_bool(
            merged.get(ENV_ALLOW_NON_LOOPBACK), default=False
        )
    else:
        resolved_allow_non_loopback = bool(allow_non_loopback)

    resolved_trace_max = resolve_numeric_setting(
        cli_value=trace_max,
        env_key=ENV_TRACE_MAX,
        default=DEFAULT_TRACE_MAX,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_request_timeout = resolve_numeric_setting(
        cli_value=request_timeout,
        env_key=ENV_REQUEST_TIMEOUT,
        default=DEFAULT_REQUEST_TIMEOUT,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_compact_timeout = resolve_numeric_setting(
        cli_value=compact_timeout,
        env_key=ENV_COMPACT_TIMEOUT,
        default=DEFAULT_COMPACT_TIMEOUT,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    if limit_min_remaining_percent is None:
        resolved_limit_min_remaining_percent = parse_percentage_float(
            merged.get(ENV_LIMIT_MIN_REMAINING_PERCENT),
            default=DEFAULT_LIMIT_MIN_REMAINING_PERCENT,
        )
    else:
        resolved_limit_min_remaining_percent = min(
            100.0, max(0.0, float(limit_min_remaining_percent))
        )

    resolved_max_in_flight_requests = (
        DEFAULT_MAX_IN_FLIGHT_REQUESTS
        if max_in_flight_requests is None
        else max(0, int(max_in_flight_requests))
    )
    if max_in_flight_requests is None:
        raw_max_in_flight = merged.get(ENV_MAX_IN_FLIGHT_REQUESTS)
        if raw_max_in_flight is not None:
            try:
                resolved_max_in_flight_requests = max(0, int(raw_max_in_flight))
            except ValueError:
                resolved_max_in_flight_requests = DEFAULT_MAX_IN_FLIGHT_REQUESTS

    resolved_max_pending_requests = (
        DEFAULT_MAX_PENDING_REQUESTS
        if max_pending_requests is None
        else max(0, int(max_pending_requests))
    )
    if max_pending_requests is None:
        raw_max_pending = merged.get(ENV_MAX_PENDING_REQUESTS)
        if raw_max_pending is not None:
            try:
                resolved_max_pending_requests = max(0, int(raw_max_pending))
            except ValueError:
                resolved_max_pending_requests = DEFAULT_MAX_PENDING_REQUESTS

    if auto_reset_on_single_key is None:
        resolved_auto_reset_on_single_key = parse_bool(
            merged.get(ENV_AUTO_RESET_ON_SINGLE_KEY),
            default=False,
        )
    else:
        resolved_auto_reset_on_single_key = bool(auto_reset_on_single_key)

    resolved_auto_reset_streak = resolve_numeric_setting(
        cli_value=auto_reset_streak,
        env_key=ENV_AUTO_RESET_STREAK,
        default=DEFAULT_AUTO_RESET_STREAK,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_auto_reset_cooldown = resolve_numeric_setting(
        cli_value=auto_reset_cooldown,
        env_key=ENV_AUTO_RESET_COOLDOWN,
        default=DEFAULT_AUTO_RESET_COOLDOWN,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_auto_heal_interval = resolve_numeric_setting(
        cli_value=auto_heal_interval,
        env_key=ENV_AUTO_HEAL_INTERVAL,
        default=DEFAULT_AUTO_HEAL_INTERVAL,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_auto_heal_success_target = resolve_numeric_setting(
        cli_value=auto_heal_success_target,
        env_key=ENV_AUTO_HEAL_SUCCESS_TARGET,
        default=DEFAULT_AUTO_HEAL_SUCCESS_TARGET,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_auto_heal_max_attempts = resolve_numeric_setting(
        cli_value=auto_heal_max_attempts,
        env_key=ENV_AUTO_HEAL_MAX_ATTEMPTS,
        default=DEFAULT_AUTO_HEAL_MAX_ATTEMPTS,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_max_ejection_percent = resolve_numeric_setting(
        cli_value=max_ejection_percent,
        env_key=ENV_MAX_EJECTION_PERCENT,
        default=DEFAULT_MAX_EJECTION_PERCENT,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    resolved_consecutive_error_threshold = resolve_numeric_setting(
        cli_value=consecutive_error_threshold,
        env_key=ENV_CONSECUTIVE_ERROR_THRESHOLD,
        default=DEFAULT_CONSECUTIVE_ERROR_THRESHOLD,
        env_parser=parse_positive_int,
        min_cli_value=1,
    )

    return Settings(
        auth_dir=resolved_auth_dir,
        host=resolved_host,
        port=resolved_port,
        upstream=resolved_upstream,
        management_key=resolved_key,
        env_file=str(resolved_env_path),
        allow_non_loopback=resolved_allow_non_loopback,
        trace_max=resolved_trace_max,
        request_timeout=resolved_request_timeout,
        compact_timeout=resolved_compact_timeout,
        limit_min_remaining_percent=resolved_limit_min_remaining_percent,
        max_in_flight_requests=resolved_max_in_flight_requests,
        max_pending_requests=resolved_max_pending_requests,
        auto_reset_on_single_key=resolved_auto_reset_on_single_key,
        auto_reset_streak=resolved_auto_reset_streak,
        auto_reset_cooldown=resolved_auto_reset_cooldown,
        auto_heal_interval=resolved_auto_heal_interval,
        auto_heal_success_target=resolved_auto_heal_success_target,
        auto_heal_max_attempts=resolved_auto_heal_max_attempts,
        max_ejection_percent=resolved_max_ejection_percent,
        consecutive_error_threshold=resolved_consecutive_error_threshold,
    )


def ensure_management_key(
    auth_dir: str, current: Optional[str], *, env_path: Optional[Path] = None
) -> str:
    key = str(current or "").strip()
    # Reject empty string and literal "None" (from corrupted env files)
    if key and key.lower() != "none":
        return key
    generated = secrets.token_urlsafe(24)
    path = env_path or env_file_path(auth_dir)
    ensure_env_file(path)
    upsert_env_values(path, {ENV_MANAGEMENT_KEY: generated})
    os.environ.setdefault(ENV_MANAGEMENT_KEY, generated)
    return generated


def format_shell_exports(values: Dict[str, str]) -> str:
    lines = []
    for key in sorted(values.keys()):
        value = values[key]
        escaped = re.sub(r"'", "'\"'\"'", value)
        lines.append(f"export {key}='{escaped}'")
    return "\n".join(lines)
