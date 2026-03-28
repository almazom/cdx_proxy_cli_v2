from __future__ import annotations

import argparse
import json
import sys
from typing import Optional
from urllib.parse import urlencode

from cdx_proxy_cli_v2.proxy.http_client import fetch_json

from cdx_proxy_cli_v2.cli.shared import (
    _healthy_base_url_or_none,
    _management_headers,
    _settings_from_args,
)


def _build_reset_path(*, name: Optional[str], state: Optional[str]) -> str:
    params: dict[str, str] = {}
    if name:
        params["name"] = str(name)
    if state:
        params["state"] = str(state)
    query = urlencode(params)
    if not query:
        return "/reset"
    return f"/reset?{query}"


def handle_reset(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    base_url = _healthy_base_url_or_none(settings)
    if base_url is None:
        return 1

    headers = _management_headers(settings)
    path = _build_reset_path(
        name=getattr(args, "name", None),
        state=getattr(args, "state", None),
    )

    try:
        result = fetch_json(
            base_url=base_url,
            path=path,
            method="POST",
            headers=headers,
            timeout=5.0,
        )
    except Exception as exc:
        print(f"Reset failed: {exc}", file=sys.stderr)
        return 1

    count = result.get("reset", 0)
    filter_info = result.get("filter", {})

    if bool(getattr(args, "json", False)):
        print(json.dumps(result, indent=2))
        return 0

    filter_str = ""
    if filter_info.get("name"):
        filter_str = f" (name={filter_info['name']})"
    elif filter_info.get("state"):
        filter_str = f" (state={filter_info['state']})"

    print(f"Reset {count} auth key(s){filter_str}")
    return 0
