from __future__ import annotations

import base64
import json
from pathlib import Path

from cdx_proxy_cli_v2.auth.store import load_auth_records


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _encode_b64url_json(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_taad_auth_store_accepts_supported_token_shapes(tmp_path: Path) -> None:
    """TaaD Functional Fit: supported auth token shapes are accepted."""
    _write_json(
        tmp_path / "primary.json",
        {"access_token": "tok-primary", "email": "primary@example.com"},
    )
    _write_json(
        tmp_path / "nested.json",
        {"tokens": {"access_token": "tok-nested", "account_id": "acc-1", "email": "nested@example.com"}},
    )
    _write_json(
        tmp_path / "openai_key.json",
        {"OPENAI_API_KEY": "tok-openai"},
    )
    _write_json(
        tmp_path / "fallback.json",
        {"api_key": "tok-fallback"},
    )

    records = load_auth_records(str(tmp_path))
    by_name = {item.name: item for item in records}

    assert set(by_name.keys()) == {"fallback.json", "nested.json", "openai_key.json", "primary.json"}
    assert by_name["primary.json"].token == "tok-primary"
    assert by_name["nested.json"].token == "tok-nested"
    assert by_name["nested.json"].account_id == "acc-1"
    assert by_name["nested.json"].email == "nested@example.com"
    assert by_name["openai_key.json"].token == "tok-openai"
    assert by_name["fallback.json"].token == "tok-fallback"


def test_taad_auth_store_prefers_email_from_id_token(tmp_path: Path) -> None:
    """TaaD Functional Fit: JWT email from id_token has priority over other email sources."""
    id_token = ".".join(
        [
            _encode_b64url_json({"alg": "none", "typ": "JWT"}),
            _encode_b64url_json({"email": "jwt@example.com"}),
            "signature",
        ]
    )
    _write_json(
        tmp_path / "jwt.json",
        {
            "email": "root@example.com",
            "tokens": {
                "access_token": "tok-jwt",
                "email": "nested@example.com",
                "id_token": id_token,
            },
        },
    )

    records = load_auth_records(str(tmp_path))

    assert len(records) == 1
    assert records[0].name == "jwt.json"
    assert records[0].email == "jwt@example.com"


def test_taad_auth_store_ignores_invalid_or_empty_token_files(tmp_path: Path) -> None:
    """TaaD Safety: invalid files must not break loading and must be ignored."""
    _write_json(tmp_path / "valid.json", {"access_token": "tok-valid"})
    (tmp_path / "invalid.json").write_text("{not-json", encoding="utf-8")
    _write_json(tmp_path / "empty_object.json", {})
    _write_json(tmp_path / "wrong_type.json", ["not", "object"])

    records = load_auth_records(str(tmp_path))

    assert len(records) == 1
    assert records[0].name == "valid.json"
    assert records[0].token == "tok-valid"
