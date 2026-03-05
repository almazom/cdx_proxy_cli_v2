from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Optional

DEFAULT_AUTH_DIR = "~/.codex/_auths"
DEFAULT_ENV_FILE = ".env"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_UPSTREAM = "https://chatgpt.com/backend-api"
DEFAULT_TRACE_MAX = 500
DEFAULT_REQUEST_TIMEOUT = 45
DEFAULT_COMPACT_TIMEOUT = 120

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

_TRUE_VALUES = {"1", "true", "yes", "on"}


def resolve_path(path: str) -> Path:
    return Path(os.path.expanduser(path))


def env_file_path(auth_dir: str) -> Path:
    explicit = os.environ.get(ENV_ENV_FILE)
    if explicit:
        return resolve_path(explicit)
    return resolve_path(auth_dir) / DEFAULT_ENV_FILE


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

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def env_path(self) -> Path:
        return env_file_path(self.auth_dir)

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
) -> Settings:
    initial_auth_dir = auth_dir or os.environ.get(ENV_AUTH_DIR) or DEFAULT_AUTH_DIR
    auth_dir_path = resolve_path(initial_auth_dir)
    env_path = env_file_path(str(auth_dir_path))
    file_env = load_env_file(env_path)
    merged = dict(file_env)
    merged.update(os.environ)

    resolved_auth_dir = str(resolve_path(auth_dir or merged.get(ENV_AUTH_DIR) or initial_auth_dir))
    resolved_host = (host or merged.get(ENV_HOST) or DEFAULT_HOST).strip() or DEFAULT_HOST

    def resolve_numeric_setting(
        *,
        cli_value: Optional[int],
        env_key: str,
        default: int,
        env_parser: Callable[[Optional[str], int], int],
        min_cli_value: int,
    ) -> int:
        if cli_value is None:
            return env_parser(merged.get(env_key), default=default)
        return max(min_cli_value, int(cli_value))

    resolved_port = resolve_numeric_setting(
        cli_value=port,
        env_key=ENV_PORT,
        default=0,
        env_parser=parse_port,
        min_cli_value=0,
    )

    resolved_upstream = (upstream or merged.get(ENV_UPSTREAM) or DEFAULT_UPSTREAM).strip() or DEFAULT_UPSTREAM
    raw_key = management_key if management_key is not None else merged.get(ENV_MANAGEMENT_KEY)
    # Handle both Python None and string "None" from env files
    key_str = str(raw_key).strip()
    resolved_key = key_str if key_str and key_str.lower() != "none" else None

    if allow_non_loopback is None:
        resolved_allow_non_loopback = parse_bool(merged.get(ENV_ALLOW_NON_LOOPBACK), default=False)
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

    return Settings(
        auth_dir=resolved_auth_dir,
        host=resolved_host,
        port=resolved_port,
        upstream=resolved_upstream,
        management_key=resolved_key,
        allow_non_loopback=resolved_allow_non_loopback,
        trace_max=resolved_trace_max,
        request_timeout=resolved_request_timeout,
        compact_timeout=resolved_compact_timeout,
    )


def ensure_management_key(auth_dir: str, current: Optional[str]) -> str:
    key = str(current or "").strip()
    # Reject empty string and literal "None" (from corrupted env files)
    if key and key.lower() != "none":
        return key
    generated = secrets.token_urlsafe(24)
    path = env_file_path(auth_dir)
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

