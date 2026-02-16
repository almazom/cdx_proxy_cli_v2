from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen


def fetch_json(
    *,
    base_url: str,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    url = f"{base_url}{path}"
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = Request(url=url, method=method, data=body, headers=req_headers)
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data:
        return {}
    return json.loads(data.decode("utf-8"))
