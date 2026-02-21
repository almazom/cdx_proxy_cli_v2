# CARD-003 — Fix _read_body() indefinite block on slow clients

**Priority:** P1  
**Complexity:** 1h  
**Source Finding:** F-P1-001

## Context

`server.py:211` calls `self.rfile.read(length)` with no read timeout. A slow client sending `Content-Length: 1000000` but only 100 bytes blocks the handler thread indefinitely.

## Goal

Add a socket read timeout to `_read_body()` to prevent indefinite blocking.

## Acceptance Criteria

1. A configurable `CLIPROXY_REQUEST_TIMEOUT` env var (default: 30s) is added to `Settings`.
2. The socket timeout is set on the request connection before `_read_body()` runs.
3. `TimeoutError` during body read results in `408 {"error": "request timeout"}`.
4. Unit test: mock slow `rfile` → expect 408 after timeout.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/server.py`
- `src/cdx_proxy_cli_v2/config/settings.py`
- `tests/proxy/test_server.py`
