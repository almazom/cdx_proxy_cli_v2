# Fusion Report — cdx_proxy_cli_v2

**Run:** 03_swarm_review_20260221_125112  
**Phase:** 3 — Mycelial Fusion  
**Input:** 6 expert analyses (29 total findings)  
**Date:** 2026-02-21

## Fusion Summary

Cross-analysis synthesis of 29 findings across 6 expert domains. Conflicts resolved. Priorities assigned P0/P1/P2. Stale SSOT tasks identified.

---

## P0 — Critical, Block Release

### F-P0-001: No per-IP rate limiting on proxy (converged: SEC + PERF)

**Sources:** SEC-HIGH-001, PERF convergence  
**Files:** `server.py:326` (`client_ip` captured but unused)  
**Risk:** Auth token exhaustion, upstream ban triggering, denial-of-service from local malicious process.  
**Action:** Implement per-IP sliding-window rate limiter before `_proxy_request()` dispatch.  
**Complexity estimate:** 2h

---

### F-P0-002: Response body size limit defined but not enforced (converged: SEC + PERF + TEST)

**Sources:** SEC-HIGH-002, PERF-LOW-005 (connection overhead), TEST-LOW-004  
**Files:** `server.py:35` (`DEFAULT_MAX_RESPONSE_BODY` unused)  
**Risk:** Memory exhaustion from malicious/misconfigured upstream.  
**Action:** Enforce chunked response reading with byte counter; return 502 on overflow.  
**Complexity estimate:** 2h

---

## P1 — Important, Fix Before Deployment

### F-P1-001: `_read_body()` blocks indefinitely on slow clients (SEC + PERF)

**Sources:** SEC-MED-003, PERF convergence  
**Files:** `server.py:211`  
**Risk:** Thread exhaustion under slow-loris style attack from localhost.  
**Action:** Set socket read timeout (e.g., 30s) on request socket before reading body.  
**Complexity estimate:** 1h

---

### F-P1-002: EventLogger opens file per write — performance bottleneck (PERF + TEST)

**Sources:** PERF-MED-002, TEST-MED-002  
**Files:** `event_log.py:62-67`  
**Risk:** Bottleneck under high request rate; filesystem lock overhead.  
**Action:** Keep persistent file handle; flush periodically; add NullEventLogger for tests.  
**Complexity estimate:** 2h

---

### F-P1-003: server.py has 5 mixed responsibilities, `_proxy_request()` is 163 lines (MAINT + TEST)

**Sources:** MAINT-HIGH-001, TEST-MED-001  
**Files:** `server.py` (full file)  
**Risk:** Hard to maintain and test; changes in one responsibility break another.  
**Action:** Extract `ProxyForwarder` class from `_proxy_request()`. ProxyHandler becomes thin glue.  
**Complexity estimate:** 3h

---

### F-P1-004: No schema validation on Settings (MAINT + SIMP)

**Sources:** MAINT-MED-002  
**Files:** `config/settings.py:190-240`  
**Risk:** Silent misconfiguration causes unexpected runtime behavior.  
**Action:** Add `validate_settings()` with range checks and startup warnings.  
**Complexity estimate:** 2h

---

### F-P1-005: Management API has no versioning (API)

**Sources:** API-HIGH-001  
**Files:** `proxy/rules.py:41-58`  
**Risk:** Breaking changes to management API are invisible to clients.  
**Action:** Add `/v1/` prefix. Keep old routes with `X-Deprecated` header.  
**Complexity estimate:** 2h

---

### F-P1-006: No concurrent stress test for auth rotation (TEST)

**Sources:** TEST-MED-003  
**Files:** `tests/auth/test_rotation.py`  
**Risk:** TASK-002 (race condition fix) lacks verification under concurrent load.  
**Action:** Add concurrent stress test: 10 threads × 100 iterations of pick+mark_result.  
**Complexity estimate:** 2h

---

### F-P1-007: `/trace` endpoint lacks pagination (API)

**Sources:** API-MED-002  
**Files:** `server.py` — trace management handler  
**Risk:** Large trace dumps cause slow responses; no way to paginate.  
**Action:** Add `?limit=N&offset=M` query params. Default limit 50.  
**Complexity estimate:** 1h

---

## P2 — Improvement, Do When Stable

### F-P2-001: ProxyHandler not unit-testable without live socket (TEST)

**Sources:** TEST-MED-001  
**Action:** Extract `ForwardRequest` dataclass from handler.  
**Complexity estimate:** 3h

---

### F-P2-002: `build_forward_headers()` dual-mode logic hard to reason about (SIMP)

**Sources:** SIMP-MED-001  
**Action:** Separate chatgpt-mode and generic paths into distinct functions.  
**Complexity estimate:** 1h

---

### F-P2-003: Hard-coded constants scattered across modules (MAINT)

**Sources:** MAINT-MED-003  
**Action:** Centralize tunable constants in `settings.py` or `constants.py`.  
**Complexity estimate:** 1h

---

### F-P2-004: PATH_REWRITE_PATTERNS order-dependent and fragile (API)

**Sources:** API-MED-003  
**Action:** Add order-validation unit test; document specificity rule.  
**Complexity estimate:** 1h

---

### F-P2-005: `/debug` endpoint leaks filesystem paths (SEC)

**Sources:** SEC-MED-004  
**Action:** Remove `auth_dir` and `event_log_file` from default response; add `verbose=true` opt-in.  
**Complexity estimate:** 1h

---

### F-P2-006: ThreadingHTTPServer creates unbounded threads (PERF)

**Sources:** PERF-HIGH-001  
**Action:** Cap max concurrent threads (e.g., 32) via custom server subclass.  
**Complexity estimate:** 2h

---

## SSOT Reconciliation Notes

| SSOT Task | Fusion Status |
|-----------|---------------|
| TASK-001 (Request Validation Hardening) | Partially open: TASK-001.3 (size limit) DONE; TASK-001.1 (header sanitization) and TASK-001.2 (rate limiting) still open |
| TASK-002 (Race Condition Fix) | Appears resolved — rotation.py uses threading.Lock throughout; verification test still needed (F-P1-006) |
| TASK-003 (TraceStore Memory Leak) | RESOLVED — deque(maxlen=500) is already bounded; SSOT should be closed |
| TASK-004 (Settings Validation) | Open — maps to F-P1-004 |
| TASK-005 (Event Log Sanitization) | DONE — SENSITIVE_FIELD_NAMES + _is_sensitive_field() implemented |
| TASK-006 (Rules Engine Refactoring) | Partially relevant — server.py split is higher priority (F-P1-003) |
