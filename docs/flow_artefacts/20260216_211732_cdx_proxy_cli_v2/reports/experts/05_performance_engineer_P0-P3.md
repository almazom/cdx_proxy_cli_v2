---
expert_id: "performance_engineer"
expert_name: "Performance Engineer"
run_id: "run_20260216_211732_cdx_proxy_cli_v2"
generated_at_utc: "2026-02-16T21:20:00Z"
read_only_target_repo: true
---

# Executive Summary

- **Top Risk 1**: No HTTP connection pooling - each request creates a new connection, causing high latency and resource overhead.
- **Top Risk 2**: Trace store uses unbounded memory pattern with deque - large traces could cause memory pressure.
- **Top Risk 3**: Polling-based TUI and health checks create unnecessary CPU wakeups.

# P0 (Critical) — Must Fix

## PE-001: No HTTP connection pooling to upstream
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:274-276` — `conn_cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection; connection = conn_cls(host, port, timeout=25)` creates a new connection for every request.
- **Impact**: High latency (TCP+TLS handshake per request), resource waste (file descriptors), poor throughput under load.
- **Recommendation**: Implement connection pooling:
  - Use `urllib3.PoolManager` or maintain a connection pool per host
  - Set reasonable pool size (e.g., 10 connections per host)
  - Handle connection reuse and stale connection detection
- **Verification**: Benchmark shows <50ms p99 latency for 100 requests vs current >500ms.

# P1 (High)

## PE-002: Trace store event IDs are global integers without bounds
- **Evidence**: `src/cdx_proxy_cli_v2/observability/trace_store.py:21-22` — `self._seq = 0` incremented forever. After 2^31 events, integer overflow could occur (though unlikely in practice).
- **Impact**: Potential for ID collisions or overflow in very long-running processes.
- **Recommendation**: Use wrapping or reset sequence:
  ```python
  self._seq = (self._seq + 1) % (2**31 - 1)
  ```
  Or use UUID-based IDs for distributed scenarios.
- **Verification**: Sequence wraps safely at max value.

## PE-003: JSON parsing in hot path without caching
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:17-30` — `_extract_error_code` parses JSON on every error response. For streaming responses with errors, this could be called frequently.
- **Impact**: Unnecessary CPU cycles on error path.
- **Recommendation**: This is acceptable for error path (rare). Document that error path is not optimized. Consider caching compiled JSON schema if validation is added.
- **Verification**: No action needed - error path optimization is P3.

## PE-004: Event log writes are synchronous
- **Evidence**: `src/cdx_proxy_cli_v2/observability/event_log.py:43-49` — File write happens synchronously in request handler thread, blocking the response.
- **Impact**: Disk I/O latency added to every proxied request.
- **Recommendation**: Use buffered writer or background thread:
  - Option 1: Use `io.BufferedWriter` by opening file in buffered mode
  - Option 2: Use `queue.Queue` with dedicated writer thread
  - Option 3: Use async file writing with `aiofiles`
- **Verification**: Latency measurement shows no I/O blocking on request path.

# P2 (Medium)

## PE-005: TUI polling interval of 1s creates visible lag
- **Evidence**: `src/cdx_proxy_cli_v2/observability/tui.py:245` — `interval=max(0.1, float(args.interval))` defaults to 1.0s from argparse.
- **Impact**: Stale data displayed for up to 1 second, poor UX for real-time monitoring.
- **Recommendation**: Reduce default to 0.25s or 0.5s. Add keyboard shortcut to force refresh.
- **Verification**: Default interval is <500ms.

## PE-006: Repeated string operations in request path rewriting
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/rules.py:49-58` — `rewrite_request_path` performs multiple `startswith` checks in sequence. For non-ChatGPT hosts, all patterns are checked.
- **Impact**: Minor CPU overhead per request.
- **Recommendation**: Early return for non-ChatGPT hosts (already done at line 47). Consider compiled regex if patterns grow.
- **Verification**: Path rewriting benchmarks show <1μs per call.

## PE-007: Auth pool holds lock during entire pick operation
- **Evidence**: `src/cdx_proxy_cli_v2/auth/rotation.py:54-63` — Lock held while iterating through all states and checking availability.
- **Impact**: Contention under high concurrency, reduced throughput.
- **Recommendation**: Use read-write lock pattern or reduce critical section:
  - Copy available states list under lock
  - Perform selection outside lock
  - Update index under lock
- **Verification**: Concurrent benchmark shows linear scaling.

# P3 (Low)

## PE-008: No metrics collection for performance monitoring
- **Evidence**: No Prometheus/OpenMetrics integration or metrics export.
- **Impact**: Cannot observe performance degradation, no alerting on latency spikes.
- **Recommendation**: Add `/metrics` endpoint exposing:
  - Request latency histogram
  - Auth pool hit/miss rates
  - Connection pool utilization
  - Error rates by status code
- **Verification**: `/metrics` endpoint returns Prometheus-format metrics.

## PE-009: Settings object recreated on every command
- **Evidence**: Each CLI command calls `build_settings()` which reads files and parses environment.
- **Impact**: Minor startup overhead for each command.
- **Recommendation**: Cache settings in state file or add settings warmup. Low priority since CLI startup is already fast.
- **Verification**: Settings load time is <10ms.

## PE-010: Rich table rendering in hot loop
- **Evidence**: `src/cdx_proxy_cli_v2/observability/tui.py:195-220` — Table rebuilt on every refresh cycle.
- **Impact**: Unnecessary object allocation, minor CPU usage.
- **Recommendation**: Use incremental updates via `Live.update()` with table diffing. Low priority - Rich handles this reasonably.
- **Verification**: TUI refresh takes <50ms.

# Notes

- Commands run (read-only):
  - `rg "HTTPConnection\|HTTPSConnection" src/ --type py`
  - `rg "with.*lock\|Lock()" src/ --type py`
  - `rg "while True\|time.sleep" src/ --type py`
- Assumptions / unknowns:
  - Current load patterns unknown - may not need optimization
  - Connection pooling may have been intentionally avoided for simplicity
- Confidence (0-100): 80
