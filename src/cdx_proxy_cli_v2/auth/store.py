from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.limits_domain import decode_jwt_payload

try:
    import keyring
    from keyring.errors import NoKeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    keyring = None  # type: ignore
    NoKeyringError = Exception  # type: ignore
    KEYRING_AVAILABLE = False

SERVICE_NAME = "cdx_proxy_cli_v2"


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
            if os.path.commonpath([str(root), str(resolved)]) != str(root):
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


def extract_auth_fields(raw: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str]]:
    token = ""
    email = _clean_text(raw.get("email"))
    account_id: Optional[str] = None

    tokens = raw.get("tokens")
    if isinstance(tokens, dict):
        token = str(tokens.get("access_token") or "")
        account_id = _clean_text(tokens.get("account_id"))
        if not email:
            email = _clean_text(tokens.get("email"))
        id_token = _clean_text(tokens.get("id_token"))
        if id_token:
            id_payload = decode_jwt_payload(id_token)
            jwt_email = _clean_text(id_payload.get("email"))
            if jwt_email:
                email = jwt_email

    if not token:
        token = str(raw.get("access_token") or "")
    if not token:
        token = str(raw.get("OPENAI_API_KEY") or "")
    if not token:
        token = str(raw.get("api_key") or raw.get("openai_api_key") or raw.get("token") or "")
    return token.strip(), email, account_id


def load_auth_records(auth_dir: str) -> List[AuthRecord]:
    """Load auth records, retrieving tokens from OS keyring when available."""
    records: List[AuthRecord] = []
    for path in iter_auth_json_files(auth_dir):
        raw, error = read_auth_json(path)
        if error or raw is None:
            continue
        token, email, account_id = extract_auth_fields(raw)
        
        # If keyring is available, try to get token from keyring first
        if KEYRING_AVAILABLE and keyring:
            try:
                keyring_token = keyring.get_password(SERVICE_NAME, path.stem)
                if keyring_token:
                    token = keyring_token
            except NoKeyringError:
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
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    
    # Store token in keyring if available
    if KEYRING_AVAILABLE and keyring:
        try:
            keyring.set_password(SERVICE_NAME, path.stem, record.token)
        except NoKeyringError:
            pass  # Token stored in file only
