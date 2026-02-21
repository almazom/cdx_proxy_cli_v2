# CARD-002 — Enforce response body size limit

**Priority:** P0  
**Complexity:** 2h  
**Source Finding:** F-P0-002  
**SSOT Ref:** null (new finding)

## Context

`server.py:35` defines `DEFAULT_MAX_RESPONSE_BODY = 10 * 1024 * 1024` but this constant is never used in `_proxy_request()`. A malicious upstream can send an unbounded response body.

## Goal

Read upstream response body in chunks, track total bytes, and abort with 502 if limit exceeded.

## Acceptance Criteria

1. `_proxy_request()` reads response body incrementally with a byte counter.
2. If response body exceeds `DEFAULT_MAX_RESPONSE_BODY`, connection is closed and client receives `502 {"error": "upstream response too large"}`.
3. Non-streaming responses: enforce limit during body accumulation.
4. Streaming responses (SSE): enforce limit per chunk; abort stream on overflow.
5. Unit test: mock upstream that returns >10MB body → expect 502.
6. Existing tests continue to pass.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/server.py` (enforce limit in response reading)
- `tests/proxy/test_server.py` (add overflow test)
