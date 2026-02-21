# CARD-001 — Implement per-IP rate limiting on proxy

**Priority:** P0  
**Complexity:** 2h  
**Source Finding:** F-P0-001  
**SSOT Ref:** TASK-001.2

## Context

`server.py:326` captures `client_ip` but never enforces any rate limit on it. A malicious local process can flood the proxy, exhausting auth tokens or triggering upstream bans.

## Goal

Implement a sliding-window per-IP rate limiter that blocks requests exceeding a configurable threshold before `_proxy_request()` runs.

## Acceptance Criteria

1. A `PerIpRateLimiter` class or function is implemented in a new `proxy/rate_limiter.py` module.
2. Default limit: 60 requests per 60s per IP (configurable via `CLIPROXY_RATE_LIMIT_RPS` env var).
3. When limit exceeded: respond `429 {"error": "rate limit exceeded"}` without forwarding upstream.
4. `client_ip=None` (e.g., Unix socket) is exempt from limiting.
5. Unit test: assert that the 61st request within 60s returns 429.
6. Existing tests continue to pass.

## Implementation Hints

- Use `collections.deque` or `time`-based sliding window per IP in a dict protected by `threading.Lock`.
- Inject `PerIpRateLimiter` into `ProxyRuntime` as an optional field with default enabled.
- Call `rate_limiter.check(client_ip)` at the top of `_handle_request()`.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/server.py` (integrate)
- `src/cdx_proxy_cli_v2/proxy/rate_limiter.py` (create)
- `src/cdx_proxy_cli_v2/config/settings.py` (add env var)
- `tests/proxy/test_rate_limiter.py` (create)
