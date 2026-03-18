"""Management endpoint handlers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from cdx_proxy_cli_v2.proxy.runtime import ProxyRuntime


def extract_error_code(raw_body: bytes) -> Optional[str]:
    """Extract error code from JSON response body.

    Args:
        raw_body: Raw response body bytes

    Returns:
        Error code string if found, None otherwise
    """
    if not raw_body:
        return None
    try:
        parsed = json.loads(raw_body.decode("utf-8", errors="replace"))
    except Exception:
        return None
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip()
        code = parsed.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return None


class ManagementHandler:
    """Handles management endpoint requests.

    Supported endpoints:
    - /debug: Server status and configuration
    - /trace: Recent trace events
    - /health: Auth pool health snapshot
    - /auth-files: List of auth file names
    - /shutdown: Graceful shutdown request
    - /reset: Reset auth key(s) to healthy state
    """

    def __init__(self, runtime: "ProxyRuntime", host: str, port: int) -> None:
        self._runtime = runtime
        self._host = host
        self._port = port

    def handle(
        self, route: str, path: str, send_json_callback, method: str = "GET"
    ) -> bool:
        """Handle a management route.

        Args:
            route: Management route name (debug, trace, health, etc.)
            path: Full request path including query string
            send_json_callback: Function to send JSON response (status, payload)

        Returns:
            True if route was handled, False if unknown route
        """
        if route == "debug":
            send_json_callback(
                200, self._runtime.debug_payload(host=self._host, port=self._port)
            )
            return True

        if route == "trace":
            limit = self._parse_limit(path)
            send_json_callback(200, self._runtime.trace_payload(limit=limit))
            return True

        if route == "health":
            refresh = self._parse_refresh(path)
            send_json_callback(200, self._runtime.health_snapshot(refresh=refresh))
            return True

        if route == "auth-files":
            send_json_callback(200, {"files": self._runtime.auth_pool.auth_files()})
            return True

        if route == "shutdown":
            send_json_callback(200, {"status": "shutting_down"})
            self._runtime.logger.write(
                level="INFO",
                event="proxy.shutdown_requested",
                message="shutdown requested",
            )
            return True

        if route == "reset":
            if method.upper() != "POST":
                send_json_callback(405, {"error": "Method not allowed. Use POST."})
                return True
            name, state = self._parse_reset_params(path)
            count = self._runtime.auth_pool.reset_auth(name=name, state=state)
            send_json_callback(
                200, {"reset": count, "filter": {"name": name, "state": state}}
            )
            self._runtime.logger.write(
                level="INFO",
                event="proxy.auth_reset",
                message=f"reset {count} auth key(s)",
                name=name,
                state=state,
                count=count,
            )
            return True

        return False

    @staticmethod
    def _parse_limit(path: str) -> int:
        """Parse limit query parameter from path."""
        query = urlsplit(path).query
        if not query:
            return 0
        params = parse_qs(query)
        try:
            return int(params.get("limit", ["0"])[0])
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _parse_refresh(path: str) -> bool:
        """Parse refresh query parameter from path."""
        query = urlsplit(path).query
        if not query:
            return False
        params = parse_qs(query)
        return params.get("refresh", ["0"])[0] == "1"

    @staticmethod
    def _parse_reset_params(path: str) -> tuple[Optional[str], Optional[str]]:
        """Parse reset query parameters from path.

        Returns:
            Tuple of (name, state) filters. Either may be None.
        """
        query = urlsplit(path).query
        if not query:
            return None, None
        params = parse_qs(query)
        name = params.get("name", [None])[0]
        state = params.get("state", [None])[0]
        return name, state
