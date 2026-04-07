from __future__ import annotations

import argparse
import json
import os
import sys

from cdx_proxy_cli_v2.cli.shared import _load_codex_auth_identity, _settings_from_args
from cdx_proxy_cli_v2.observability.collective_dashboard import (
    build_collective_payload,
    build_collective_payload_from_accounts,
    render_collective_dashboard,
)
from cdx_proxy_cli_v2.runtime.service import service_status

from cdx_proxy_cli_v2.cli.shared import (
    DOCTOR_HEALTH_TIMEOUT_SECONDS,
    _fetch_health_accounts,
    _management_headers,
)


def handle_all(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    status_payload = service_status(settings)
    usage_base_url = (
        os.environ.get("CLIPROXY_USAGE_BASE_URL") or "https://chatgpt.com/backend-api"
    )
    current_access_token = os.environ.get("OPENAI_API_KEY")
    current_file = os.environ.get("CLIPROXY_CURRENT_AUTH_FILE")
    codex_access_token, codex_email, codex_account_id = _load_codex_auth_identity()
    if not current_access_token:
        current_access_token = codex_access_token

    payload = None
    if bool(status_payload.get("healthy")):
        base_url = str(status_payload.get("base_url") or settings.base_url)
        try:
            accounts = _fetch_health_accounts(
                base_url=base_url,
                headers=_management_headers(settings),
                timeout=DOCTOR_HEALTH_TIMEOUT_SECONDS,
            )
            payload = build_collective_payload_from_accounts(
                accounts=accounts,
                warn_at=int(args.warn_at),
                cooldown_at=int(args.cooldown_at),
                only=str(args.only),
                current_access_token=current_access_token,
                current_file=current_file,
                current_email=codex_email,
                current_account_id=codex_account_id,
            )
        except Exception:
            payload = None

    if payload is None:
        try:
            payload = build_collective_payload(
                auths_dir=settings.auth_dir,
                base_url=usage_base_url,
                warn_at=int(args.warn_at),
                cooldown_at=int(args.cooldown_at),
                timeout=int(args.timeout),
                only=str(args.only),
                prefer_keyring=False,
                current_access_token=current_access_token,
                current_file=current_file,
                current_email=codex_email,
                current_account_id=codex_account_id,
            )
        except Exception as exc:
            print(f"cdx all failed to build offline snapshot: {exc}", file=sys.stderr)
            return 1
    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    render_collective_dashboard(payload)
    return 0
