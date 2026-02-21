# CARD-012 — Cap ThreadingHTTPServer max concurrent threads

**Priority:** P2  
**Complexity:** 2h  
**Source Finding:** F-P2-006

## Goal

Add a max-threads cap to `ProxyHTTPServer` to prevent thread exhaustion under burst load.

## Acceptance Criteria

1. `ProxyHTTPServer` subclasses `ThreadingHTTPServer` with a `ThreadPoolExecutor` or semaphore cap.
2. Default cap: 32 threads (configurable via `CLIPROXY_MAX_THREADS` env var).
3. When cap reached: new connections are queued (not dropped).
4. Tests pass.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/server.py`
- `src/cdx_proxy_cli_v2/config/settings.py`
