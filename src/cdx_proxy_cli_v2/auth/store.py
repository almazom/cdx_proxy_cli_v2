from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cdx_proxy_cli_v2.auth.models import AuthRecord
from cdx_proxy_cli_v2.limits_domain import decode_jwt_payload


def iter_auth_json_files(auth_dir: str) -> List[Path]:
    root = Path(os.path.expanduser(auth_dir))
    try:
        entries = sorted(root.iterdir())
    except (FileNotFoundError, PermissionError, OSError):
        return []
    files: List[Path] = []
    for entry in entries:
        try:
            if entry.is_file() and entry.suffix.lower() == ".json":
                files.append(entry)
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
    records: List[AuthRecord] = []
    for path in iter_auth_json_files(auth_dir):
        raw, error = read_auth_json(path)
        if error or raw is None:
            continue
        token, email, account_id = extract_auth_fields(raw)
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
