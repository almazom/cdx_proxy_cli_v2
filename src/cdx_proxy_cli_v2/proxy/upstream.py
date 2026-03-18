from __future__ import annotations

import http.client
import json
import select
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from cdx_proxy_cli_v2.proxy.models import _extract_error_code, _normalize_models_response_body
from cdx_proxy_cli_v2.proxy.rules import get_request_timeout


@dataclass
class UpstreamAttemptResult:
    status: int
    headers: List[Tuple[str, str]]
    body: bytes
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    stream_response: Optional[http.client.HTTPResponse] = None
    stream_connection: Optional[http.client.HTTPConnection] = None
    websocket_upgrade: bool = False


def _header_value_case_insensitive(headers: Dict[str, str], key: str) -> str:
    for existing_key, value in headers.items():
        if existing_key.lower() == key.lower():
            return str(value)
    return ""


def _is_websocket_upgrade_request(headers: Dict[str, str]) -> bool:
    upgrade = _header_value_case_insensitive(headers, "Upgrade").strip().lower()
    connection = _header_value_case_insensitive(headers, "Connection").strip().lower()
    if upgrade != "websocket":
        return False
    connection_tokens = {
        token.strip() for token in connection.split(",") if token.strip()
    }
    return "upgrade" in connection_tokens


def _tunnel_websocket(
    *,
    client_socket: object,
    client_writer: object,
    upstream_connection: http.client.HTTPConnection,
    upstream_response: http.client.HTTPResponse,
) -> None:
    upstream_socket = getattr(upstream_connection, "sock", None)
    if upstream_socket is None:
        raise RuntimeError("upstream websocket socket unavailable")

    try:
        flush = getattr(client_writer, "flush")
        flush()
    except Exception:
        pass

    sockets = [client_socket, upstream_socket]
    try:
        for sock in sockets:
            try:
                sock.settimeout(None)
            except Exception:
                pass

        while True:
            readable, _, exceptional = select.select(sockets, [], sockets)
            if exceptional:
                break
            for source in readable:
                try:
                    chunk = source.recv(65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    return
                target = upstream_socket if source is client_socket else client_socket
                target.sendall(chunk)
    finally:
        try:
            upstream_response.close()
        except Exception:
            pass
        try:
            upstream_connection.close()
        except Exception:
            pass


def _run_upstream_attempt(
    *,
    command: str,
    scheme: str,
    host: str,
    port: int,
    rewritten_path: str,
    full_path: str,
    body: bytes,
    headers: Dict[str, str],
    request_timeout: int,
    compact_timeout: int,
    max_response_body: int,
) -> UpstreamAttemptResult:
    connection: Optional[http.client.HTTPConnection] = None
    try:
        conn_cls = (
            http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        )
        timeout = get_request_timeout(
            rewritten_path,
            default=request_timeout,
            compact=compact_timeout,
        )
        connection = conn_cls(host, port, timeout=timeout)
        connection._http_vsn = 11  # type: ignore[attr-defined]
        connection._http_vsn_str = "HTTP/1.1"  # type: ignore[attr-defined]
        connection.request(command, full_path, body=body, headers=headers)
        response = connection.getresponse()
        status = response.status
        response_headers = response.getheaders()
        upgrade_header = str(response.getheader("Upgrade") or "")
        if status == 101 and upgrade_header.lower() == "websocket":
            stream_connection = connection
            connection = None
            return UpstreamAttemptResult(
                status=status,
                headers=response_headers,
                body=b"",
                stream_response=response,
                stream_connection=stream_connection,
                websocket_upgrade=True,
            )

        content_type = str(response.getheader("Content-Type") or "")
        if "text/event-stream" in content_type.lower():
            stream_connection = connection
            connection = None
            return UpstreamAttemptResult(
                status=status,
                headers=response_headers,
                body=b"",
                stream_response=response,
                stream_connection=stream_connection,
            )

        data = response.read(max_response_body + 1)
        if len(data) > max_response_body:
            return UpstreamAttemptResult(
                status=413,
                headers=[("Content-Type", "application/json")],
                body=json.dumps({"error": "response body too large"}).encode("utf-8"),
            )
        data = _normalize_models_response_body(data, request_path=rewritten_path)
        return UpstreamAttemptResult(
            status=status,
            headers=response_headers,
            body=data,
            error_code=_extract_error_code(data, status=status),
        )
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)
        return UpstreamAttemptResult(
            status=502,
            headers=[("Content-Type", "application/json")],
            body=json.dumps(
                {"error": "upstream request failed", "detail": error_message}
            ).encode("utf-8"),
            error_message=error_message,
            error_code="upstream_request_failed",
        )
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
