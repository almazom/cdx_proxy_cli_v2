from __future__ import annotations

import argparse
import json
import sys

from cdx_proxy_cli_v2.cli.doctor_view import (
    _doctor_payload,
    _render_doctor_table,
    _render_probe_results,
)
from cdx_proxy_cli_v2.proxy.http_client import fetch_json

from cdx_proxy_cli_v2.cli.shared import (
    DOCTOR_HEALTH_TIMEOUT_SECONDS,
    DOCTOR_POLICY,
    _fetch_health_accounts,
    _healthy_base_url_or_none,
    _management_headers,
    _settings_from_args,
)


def handle_doctor(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    base_url = _healthy_base_url_or_none(settings)
    if base_url is None:
        return 1

    headers = _management_headers(settings)

    # Handle --probe flag: proactively test auth keys
    if getattr(args, "probe", False):
        timeout = getattr(args, "probe_timeout", 10)
        timeout = max(1, min(30, timeout))

        try:
            probe_payload = fetch_json(
                base_url=base_url,
                path=f"/probe?timeout={timeout}",
                method="POST",
                headers=headers,
                timeout=float(timeout) + 5.0,
            )
        except Exception as exc:
            print(f"Probe failed: {exc}", file=sys.stderr)
            return 1

        _render_probe_results(probe_payload, json_mode=bool(args.json))

        if bool(args.json):
            try:
                accounts = _fetch_health_accounts(
                    base_url=base_url,
                    headers=headers,
                    timeout=DOCTOR_HEALTH_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                print(
                    f"Doctor failed to read /health after probe: {exc}", file=sys.stderr
                )
                return 1

            output = _doctor_payload(
                base_url=base_url,
                accounts=accounts,
                policy=DOCTOR_POLICY,
                probe=probe_payload,
            )
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

    # Regular doctor flow
    try:
        accounts = _fetch_health_accounts(
            base_url=base_url,
            headers=headers,
            timeout=DOCTOR_HEALTH_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        print(f"Doctor failed to read /health: {exc}", file=sys.stderr)
        return 1

    payload = _doctor_payload(
        base_url=base_url, accounts=accounts, policy=DOCTOR_POLICY
    )
    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    _render_doctor_table(accounts, payload["summary"])
    return 0
