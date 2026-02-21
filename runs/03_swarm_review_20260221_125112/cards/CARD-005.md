# CARD-005 — Split server.py: extract ProxyForwarder class

**Priority:** P1  
**Complexity:** 3h  
**Source Finding:** F-P1-003  
**SSOT Ref:** TASK-006

## Context

`server.py` is 527 lines with `ProxyRuntime`, `ProxyHTTPServer`, `ProxyHandler`, and `_proxy_request()` (163 lines) all combined. This makes testing and maintenance difficult.

## Goal

Extract `_proxy_request()` logic into a `ProxyForwarder` class in `proxy/forwarder.py`. `ProxyHandler` becomes thin glue code (<50 lines).

## Acceptance Criteria

1. `ProxyForwarder` class created in `src/cdx_proxy_cli_v2/proxy/forwarder.py`.
2. `ProxyForwarder.forward(context)` accepts a `ForwardRequest` dataclass (method, path, headers, body, client_ip).
3. `ProxyForwarder.forward()` returns a `ForwardResponse` (status, headers, body).
4. `ProxyHandler._proxy_request()` calls `ProxyForwarder.forward()` and writes the response.
5. All existing `tests/proxy/test_server.py` tests pass after refactor.
6. `ForwardRequest` and `ForwardResponse` are unit-testable without a socket.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/server.py` (thin down)
- `src/cdx_proxy_cli_v2/proxy/forwarder.py` (create)
- `tests/proxy/test_forwarder.py` (create)

## Dependencies

None (can proceed independently).
