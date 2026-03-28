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


def _resolve_startup_env_path(
    auth_dir_path: Path,
    *,
    auth_dir: Optional[str],
    env_file: Optional[str] = None,
) -> Path:
    if env_file is not None:
        return resolve_path(env_file)

    require_auth_dir_scope = auth_dir is not None or bool(os.environ.get(ENV_AUTH_DIR))
    inherited_env_file = _resolve_inherited_env_file_path(
        str(auth_dir_path),
        None if auth_dir is not None else os.environ.get(ENV_ENV_FILE),
        require_auth_dir_scope=require_auth_dir_scope,
    )
    return inherited_env_file or env_file_path(str(auth_dir_path))


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
    env_path = _resolve_startup_env_path(
        auth_dir_path,
        auth_dir=auth_dir,
        env_file=env_file,
    )
    merged = load_env_file(env_path)
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


# Declarative spec for numeric settings resolved via _resolve_spec_int().
# Each tuple: (kwarg_name, field_name, env_key, default, parser, min_cli)
_NUMERIC_SPECS: list[tuple[str, str, str, int, Callable[[Optional[str], int], int], int]] = [
    ("trace_max", "trace_max", ENV_TRACE_MAX, DEFAULT_TRACE_MAX, parse_positive_int, 1),
    ("request_timeout", "request_timeout", ENV_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT, parse_positive_int, 1),
    ("compact_timeout", "compact_timeout", ENV_COMPACT_TIMEOUT, DEFAULT_COMPACT_TIMEOUT, parse_positive_int, 1),
    ("auto_reset_streak", "auto_reset_streak", ENV_AUTO_RESET_STREAK, DEFAULT_AUTO_RESET_STREAK, parse_positive_int, 1),
    ("auto_reset_cooldown", "auto_reset_cooldown", ENV_AUTO_RESET_COOLDOWN, DEFAULT_AUTO_RESET_COOLDOWN, parse_positive_int, 1),
    ("auto_heal_interval", "auto_heal_interval", ENV_AUTO_HEAL_INTERVAL, DEFAULT_AUTO_HEAL_INTERVAL, parse_positive_int, 1),
    ("auto_heal_success_target", "auto_heal_success_target", ENV_AUTO_HEAL_SUCCESS_TARGET, DEFAULT_AUTO_HEAL_SUCCESS_TARGET, parse_positive_int, 1),
    ("auto_heal_max_attempts", "auto_heal_max_attempts", ENV_AUTO_HEAL_MAX_ATTEMPTS, DEFAULT_AUTO_HEAL_MAX_ATTEMPTS, parse_positive_int, 1),
    ("max_ejection_percent", "max_ejection_percent", ENV_MAX_EJECTION_PERCENT, DEFAULT_MAX_EJECTION_PERCENT, parse_positive_int, 1),
    ("consecutive_error_threshold", "consecutive_error_threshold", ENV_CONSECUTIVE_ERROR_THRESHOLD, DEFAULT_CONSECUTIVE_ERROR_THRESHOLD, parse_positive_int, 1),
]


def _resolve_spec_int(
    cli_value: Optional[int],
    merged_env: Dict[str, str],
    env_key: str,
    default: int,
    env_parser: Callable[[Optional[str], int], int],
    min_cli_value: int,
) -> int:
    if cli_value is None:
        return env_parser(merged_env.get(env_key), default)
    return max(min_cli_value, int(cli_value))


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
    # --- resolve env sources ---
    initial_auth_dir = auth_dir or os.environ.get(ENV_AUTH_DIR) or DEFAULT_AUTH_DIR
    auth_dir_path = resolve_path(initial_auth_dir)
    env_path = _resolve_startup_env_path(auth_dir_path, auth_dir=auth_dir)
    file_env = load_env_file(env_path)
    merged = dict(file_env)
    merged.update(os.environ)

    # --- special-case: paths and strings ---
    resolved_auth_dir = str(auth_dir_path)
    resolved_env_path = env_file_path(resolved_auth_dir) if auth_dir is not None else env_path
    resolved_host = (host or merged.get(ENV_HOST) or DEFAULT_HOST).strip() or DEFAULT_HOST
    resolved_upstream = normalize_upstream(
        upstream or merged.get(ENV_UPSTREAM) or DEFAULT_UPSTREAM, default=DEFAULT_UPSTREAM,
    )

    # --- special-case: port (range-validated) ---
    resolved_port = _resolve_spec_int(port, merged, ENV_PORT, 0, parse_port, 0)
    if not (0 <= resolved_port <= 65535):
        raise ValueError("port must be between 0 and 65535")

    # --- special-case: management key (strip "None" strings) ---
    raw_key = management_key if management_key is not None else merged.get(ENV_MANAGEMENT_KEY)
    key_str = str(raw_key).strip()
    resolved_key = key_str if key_str and key_str.lower() != "none" else None

    # --- special-case: booleans ---
    resolved_allow_non_loopback = (
        bool(allow_non_loopback)
        if allow_non_loopback is not None
        else parse_bool(merged.get(ENV_ALLOW_NON_LOOPBACK), default=False)
    )
    resolved_auto_reset_on_single_key = (
        bool(auto_reset_on_single_key)
        if auto_reset_on_single_key is not None
        else parse_bool(merged.get(ENV_AUTO_RESET_ON_SINGLE_KEY), default=False)
    )

    # --- special-case: percentage float ---
    resolved_limit_min_remaining_percent = (
        min(100.0, max(0.0, float(limit_min_remaining_percent)))
        if limit_min_remaining_percent is not None
        else parse_percentage_float(
            merged.get(ENV_LIMIT_MIN_REMAINING_PERCENT), default=DEFAULT_LIMIT_MIN_REMAINING_PERCENT,
        )
    )

    # --- special-case: in-flight/pending (allow 0, with env fallback) ---
    def _resolve_non_negative(cli_val: Optional[int], env_key: str, default: int) -> int:
        if cli_val is not None:
            return max(0, cli_val)
        raw = merged.get(env_key)
        if raw is not None:
            try:
                return max(0, int(raw))
            except ValueError:
                return default
        return default

    resolved_max_in_flight = _resolve_non_negative(max_in_flight_requests, ENV_MAX_IN_FLIGHT_REQUESTS, DEFAULT_MAX_IN_FLIGHT_REQUESTS)
    resolved_max_pending = _resolve_non_negative(max_pending_requests, ENV_MAX_PENDING_REQUESTS, DEFAULT_MAX_PENDING_REQUESTS)

    # --- declarative numeric specs ---
    cli_overrides = {
        "trace_max": trace_max,
        "request_timeout": request_timeout,
        "compact_timeout": compact_timeout,
        "auto_reset_streak": auto_reset_streak,
        "auto_reset_cooldown": auto_reset_cooldown,
        "auto_heal_interval": auto_heal_interval,
        "auto_heal_success_target": auto_heal_success_target,
        "auto_heal_max_attempts": auto_heal_max_attempts,
        "max_ejection_percent": max_ejection_percent,
        "consecutive_error_threshold": consecutive_error_threshold,
    }
    spec_resolved: dict[str, int] = {}
    for kwarg, field, env_key, default, parser, min_val in _NUMERIC_SPECS:
        spec_resolved[field] = _resolve_spec_int(cli_overrides[kwarg], merged, env_key, default, parser, min_val)

    return Settings(
        auth_dir=resolved_auth_dir,
        host=resolved_host,
        port=resolved_port,
        upstream=resolved_upstream,
        management_key=resolved_key,
        env_file=str(resolved_env_path),
        allow_non_loopback=resolved_allow_non_loopback,
        limit_min_remaining_percent=resolved_limit_min_remaining_percent,
        max_in_flight_requests=resolved_max_in_flight,
        max_pending_requests=resolved_max_pending,
        auto_reset_on_single_key=resolved_auto_reset_on_single_key,
        **spec_resolved,
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
