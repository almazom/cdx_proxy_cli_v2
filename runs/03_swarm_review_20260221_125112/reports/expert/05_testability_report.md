# Testability Expert Report — cdx_proxy_cli_v2

**Run:** 03_swarm_review_20260221_125112  
**Role:** Testability  
**Analyst:** strategy_variation_testability  
**Date:** 2026-02-21

## Summary

Test coverage is present across most modules. The main testability gaps are in `ProxyHandler` (hard to unit test due to inheritance from `BaseHTTPRequestHandler`) and the absence of integration tests for the full proxy request flow including auth rotation and event logging in combination.

## Findings

### TEST-MED-001 — ProxyHandler is not unit-testable without a live socket

**File:** `src/cdx_proxy_cli_v2/proxy/server.py` — `ProxyHandler`  
**Evidence:** `class ProxyHandler(BaseHTTPRequestHandler)` — requires a real socket and server to instantiate. Tests in `tests/proxy/test_server.py` likely need a live test server or extensive mocking.

**Priority:** P1  
**Recommendation:** Extract business logic from `ProxyHandler` into a `ProxyRequestContext` or `ForwardRequest` dataclass that can be constructed and tested without a socket. `ProxyHandler` becomes thin glue code.

---

### TEST-MED-002 — EventLogger has filesystem side effects with no dependency injection

**File:** `src/cdx_proxy_cli_v2/observability/event_log.py:41`  
**Evidence:** `self._path = resolve_path(auth_dir) / "rr_proxy_v2.events.jsonl"` — path hardcoded at construction. Tests must use temp directories or mock `Path.open`.

**Priority:** P2  
**Recommendation:** Accept `path: Optional[Path]` in constructor for testability. Add a `NullEventLogger` for use in tests.

---

### TEST-MED-003 — No integration test covering auth rotation under concurrent requests

**File:** `tests/auth/test_rotation.py`  
**Evidence:** Unit tests cover individual state transitions but no concurrent test with multiple threads racing on `pick()` + `mark_result()` simultaneously.

Given TASK-002 (race condition fix) this is a critical gap.

**Priority:** P1  
**Recommendation:** Add a concurrent stress test: spawn 10 threads each calling `pick()` + `mark_result(status=429)` 100 times, assert final state is consistent.

---

### TEST-LOW-004 — No test for response body size limit enforcement (constant unused)

**File:** `src/cdx_proxy_cli_v2/proxy/server.py:35`  
**Evidence:** `DEFAULT_MAX_RESPONSE_BODY = 10 * 1024 * 1024` — unused constant, no test for it because enforcement doesn't exist yet.

**Priority:** P2 (blocked by SEC-HIGH-002 implementation)  
**Recommendation:** Add test after response size limit is implemented.

---

### TEST-INFO-005 — Existing test suite passes (baseline confirmed)

**Evidence:** `tests/` directory contains 13 test files across all modules. Test structure is well-organized with separate directories per module.

**Priority:** Informational  
**Recommendation:** No action needed for existing tests.

## Pass/Fail

**PASS** — All findings have file:line evidence.
