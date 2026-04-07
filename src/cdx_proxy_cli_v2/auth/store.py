from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.limits_domain import decode_jwt_payload

try:
    import keyring

    KEYRING_AVAILABLE = True
except ImportError:
    keyring = None  # type: ignore
    KEYRING_AVAILABLE = False

SERVICE_NAME = "cdx_proxy_cli_v2"
_TOP_LEVEL_AUTH_KEYS = (
    "email",
    "access_token",
    "OPENAI_API_KEY",
    "api_key",
    "openai_api_key",
    "token",
)
_TOP_LEVEL_TOKEN_KEYS = _TOP_LEVEL_AUTH_KEYS[1:]
_NESTED_AUTH_KEYS = ("access_token", "account_id", "email", "id_token")


def iter_auth_json_files(auth_dir: str) -> List[Path]:
    """Iterate over auth JSON files, preventing path traversal attacks."""
    root = Path(os.path.expanduser(auth_dir)).resolve()
    try:
        entries = sorted(root.iterdir())
    except (FileNotFoundError, PermissionError, OSError):
        return []
    files: List[Path] = []
    for entry in entries:
        try:
            resolved = entry.resolve()
            # Prevent symlink attacks - ensure file is within auth directory
            if not resolved.is_relative_to(root):
                continue
            if resolved.is_file() and resolved.suffix.lower() == ".json":
                files.append(resolved)
        except OSError:
            continue
    return files


def read_auth_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "invalid_json"
    if not isinstance(data, dict):
        return None, "json_not_object"
    return data, None


def _clean_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _first_clean_text(raw: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = _clean_text(raw.get(key))
        if value:
            return value
    return None


def extract_auth_fields(
    raw: Dict[str, Any],
) -> Tuple[str, Optional[str], Optional[str]]:
    token = ""
    email = _first_clean_text(raw, ("email",))
    account_id: Optional[str] = None

    tokens = raw.get("tokens")
    if isinstance(tokens, dict):
        token = _first_clean_text(tokens, ("access_token",)) or ""
        account_id = _first_clean_text(tokens, ("account_id",))
        email = email or _first_clean_text(tokens, ("email",))
        id_token = _first_clean_text(tokens, ("id_token",))
        if id_token:
            id_payload = decode_jwt_payload(id_token)
            jwt_email = _first_clean_text(id_payload, ("email",))
            if jwt_email:
                email = jwt_email

    if not token:
        token = _first_clean_text(raw, _TOP_LEVEL_TOKEN_KEYS) or ""
    return token, email, account_id


def _looks_like_auth_record(raw: Dict[str, Any]) -> bool:
    """Return True only for JSON payloads that resemble auth records."""
    if _first_clean_text(raw, _TOP_LEVEL_AUTH_KEYS):
        return True

    tokens = raw.get("tokens")
    if not isinstance(tokens, dict):
        return False

    return _first_clean_text(tokens, _NESTED_AUTH_KEYS) is not None


def load_auth_records(
    auth_dir: str, *, prefer_keyring: bool = True
) -> List[AuthRecord]:
    """Load auth records, optionally preferring tokens stored in OS keyring."""
    records: List[AuthRecord] = []
    for path in iter_auth_json_files(auth_dir):
        raw, error = read_auth_json(path)
        if error or raw is None:
            continue
        if not _looks_like_auth_record(raw):
            continue
        token, email, account_id = extract_auth_fields(raw)

        # Runtime paths can skip keyring when a file token already exists to avoid
        # blocking on external keyring backends during proxy startup.
        should_query_keyring = (
            KEYRING_AVAILABLE and keyring and (prefer_keyring or not token)
        )
        if should_query_keyring:
            try:
                keyring_token = keyring.get_password(SERVICE_NAME, path.stem)
                if keyring_token:
                    token = keyring_token
            except Exception:
                pass  # Fall back to file-based token

        # Skip if still no token
        if not token:
            continue

        records.append(
            AuthRecord(
                name=path.name,
                path=str(path),
                token=token,
                email=email,
                account_id=account_id,
            )
        )
    return records


def save_auth_record(auth_dir: str, record: AuthRecord) -> None:
    """Save auth record, storing token in OS keyring when available."""
    path = Path(os.path.expanduser(auth_dir)) / record.name

    # Store non-token data in JSON file
    data: Dict[str, Any] = {}
    if record.email:
        data["email"] = record.email
    if record.account_id:
        data["tokens"] = {"account_id": record.account_id}

    token_in_keyring = False
    if KEYRING_AVAILABLE and keyring:
        try:
            keyring.set_password(SERVICE_NAME, path.stem, record.token)
            token_in_keyring = True
        except Exception:
            token_in_keyring = False

    if not token_in_keyring:
        data["access_token"] = record.token

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
