# Performance Scout Report

- The largest hot-path inefficiency remains upstream connection churn.
- Additional cost comes from unconditional error-code parsing and synchronous per-attempt logging.

## Findings

1. **P1 — no upstream connection reuse**
   - Reference: `src/cdx_proxy_cli_v2/proxy/server.py:300`
   - Impact: repeated TCP/TLS setup increases latency and reduces throughput.

2. **P1 — error-code extraction parses full bodies on non-stream responses**
   - Reference: `src/cdx_proxy_cli_v2/proxy/server.py:38`
   - Impact: extra CPU/allocation cost on successful responses.

3. **P2 — per-attempt event logging is synchronous**
   - References: `src/cdx_proxy_cli_v2/proxy/server.py:453`, `src/cdx_proxy_cli_v2/observability/event_log.py:69`
   - Impact: disk latency can bleed into request latency under concurrency.

## Top Recommendation

Connection pooling remains the most direct performance win, but it is deferred from this run in favor of security and CLI contract fixes.
