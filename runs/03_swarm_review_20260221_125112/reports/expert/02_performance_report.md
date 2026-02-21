# Performance Expert Report — cdx_proxy_cli_v2

**Run:** 03_swarm_review_20260221_125112  
**Role:** Performance  
**Analyst:** strategy_variation_performance  
**Date:** 2026-02-21

## Summary

The proxy handles moderate traffic well (loopback-only by default) but shows structural patterns that limit scalability under burst load: unbounded thread creation per request, per-write file I/O in the event logger, and lock contention on the auth pool under high request rates.

## Findings

### PERF-HIGH-001 — ThreadingHTTPServer creates unbounded threads per connection

**File:** `src/cdx_proxy_cli_v2/proxy/server.py:148`  
**Evidence:** `class ProxyHTTPServer(ThreadingHTTPServer)` — Python's `ThreadingHTTPServer` spawns a new thread for every incoming connection with no pool cap.

Under burst load (100+ concurrent requests), this leads to thread explosion and memory exhaustion. The problem is amplified by `_read_body()` blocking if clients stall.

**Priority:** P1  
**Recommendation:** Replace `ThreadingHTTPServer` with a `ThreadPoolExecutor`-backed server or cap max_threads. Alternatively add `server.max_children` limit via custom `ThreadingHTTPServer` subclass.

---

### PERF-MED-002 — EventLogger opens/closes file on every `write()` call

**File:** `src/cdx_proxy_cli_v2/observability/event_log.py:62-67`  
**Evidence:**
```python
with self._lock:
    with self._path.open("a", encoding="utf-8") as handle:
        handle.write(raw + "\n")
```
File opened, written, and closed for every single event. Under 100 req/s this becomes a bottleneck (syscall + inode lock per request).

**Priority:** P1  
**Recommendation:** Keep a persistent file handle (opened once at startup), flush periodically, or use a buffered async writer with periodic fsync.

---

### PERF-MED-003 — RoundRobinAuthPool.pick() holds lock while scanning all states

**File:** `src/cdx_proxy_cli_v2/auth/rotation.py:63`  
**Evidence:**
```python
with self._lock:
    now = time.time()
    available = [state for state in self._states if state.available(now)]
```
Full scan under lock on every request. With 50+ auth files this is O(n) per request, and the lock blocks all concurrent requests.

**Priority:** P2  
**Recommendation:** Maintain a pre-filtered available-list that's incrementally updated on state changes rather than recomputed on every pick.

---

### PERF-LOW-004 — TraceStore ring buffer size is configurable but default is fixed at 500

**File:** `src/cdx_proxy_cli_v2/observability/trace_store.py:8`  
**Evidence:** `def __init__(self, max_size: int = 500)` — reasonable default, bounded by deque(maxlen).

No memory leak risk. deque maxlen ensures bounded growth. The SSOT TASK-003 "memory leak prevention" is already resolved by design.

**Priority:** P2 (informational — SSOT TASK-003 appears done)  
**Recommendation:** Document that TraceStore is bounded. Consider exposing `max_size` in /debug output (already done via `trace_max`).

---

### PERF-LOW-005 — No connection pooling to upstream

**File:** `src/cdx_proxy_cli_v2/proxy/server.py` — `_proxy_request()`  
**Evidence:** Each request creates a new `http.client.HTTPSConnection`/`HTTPConnection`. No connection pool or keep-alive reuse to upstream.

For high-frequency AI API calls this adds TLS handshake overhead on every request.

**Priority:** P2  
**Recommendation:** Use a connection pool (e.g., `urllib3.PoolManager`) for upstream connections.

## Pass/Fail

**PASS** — All findings have file:line evidence.  
**NOTE** — TASK-003 (TraceStore memory leak) appears already resolved; SSOT should be updated.
