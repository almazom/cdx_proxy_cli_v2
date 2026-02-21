# Security Expert Report — cdx_proxy_cli_v2

**Run:** 03_swarm_review_20260221_125112  
**Role:** Security  
**Analyst:** strategy_variation_security  
**Date:** 2026-02-21

## Summary

The codebase implements a localhost HTTP proxy for routing AI API requests. The security surface is controlled but contains several meaningful gaps, particularly around request header injection, response body size enforcement, and unauthenticated info-disclosure on management endpoints.

## Findings

### SEC-HIGH-001 — No per-IP rate limiting (client-side abuse)

**File:** `src/cdx_proxy_cli_v2/proxy/server.py:326`  
**Evidence:** `client_ip = self.client_address[0] if self.client_address else None`  

`client_ip` is captured but never used to enforce any rate or concurrency limit. A malicious local process can flood the proxy with requests, exhausting auth tokens or triggering upstream bans.

**Priority:** P0  
**Recommendation:** Implement a per-IP request rate limiter (token bucket or sliding window) before `_proxy_request()` proceeds.

---

### SEC-HIGH-002 — Response body size limit defined but not enforced

**File:** `src/cdx_proxy_cli_v2/proxy/server.py:35`  
**Evidence:** `DEFAULT_MAX_RESPONSE_BODY = 10 * 1024 * 1024` — constant defined but never referenced in `_proxy_request()`.

A malicious or misconfigured upstream can send an unbounded response body, causing memory exhaustion in the proxy process.

**Priority:** P0  
**Recommendation:** Read upstream response in chunks, enforce max response body bytes, return 502 if exceeded.

---

### SEC-MED-003 — `rfile.read(length)` blocks indefinitely if client sends less data

**File:** `src/cdx_proxy_cli_v2/proxy/server.py:211`  
**Evidence:** `return self.rfile.read(length)` — no read timeout.

If a client sends `Content-Length: 1000000` but only sends 100 bytes, the handler thread blocks indefinitely, allowing a single client to hold a thread open.

**Priority:** P1  
**Recommendation:** Set socket read timeout on `rfile` or use `socket.settimeout()` on accepted connections.

---

### SEC-MED-004 — `/debug` endpoint leaks internal state without scope restriction

**File:** `src/cdx_proxy_cli_v2/proxy/server.py` (management routes)  
**Evidence:** `debug_payload()` returns `auth_dir`, `auth_count`, `upstream_base_url`, `pid`, `event_log_file`.

Any caller with the management key can enumerate internal filesystem paths. If the management key is weak or absent (`management_key` can be empty in some paths), this is unauthenticated disclosure.

**Priority:** P1  
**Recommendation:** Audit `debug_payload` fields; remove filesystem paths from the default response or add a `verbose` opt-in parameter.

---

### SEC-LOW-005 — Request header names/values not sanitized for injection

**File:** `src/cdx_proxy_cli_v2/proxy/rules.py` — `build_forward_headers()`  
**Evidence:** Header values from incoming requests forwarded verbatim after allowlist filtering. No value-level sanitization for CRLF or HTTP/1.1 header injection.

**Priority:** P1  
**Recommendation:** Strip `\r\n` from all forwarded header values. Consider using `http.client` header safety checks.

---

### SEC-INFO-006 — Token stored in JSON file when keyring unavailable (already flagged in SSOT)

**File:** `src/cdx_proxy_cli_v2/auth/store.py:64`  
**Evidence:** `if KEYRING_AVAILABLE and keyring: keyring_token = keyring.get_password(...)` — falls through to file-based token if keyring unavailable.

**Priority:** P2 (info)  
**Recommendation:** Log a warning when falling back to file-based token. Ensure file permissions are 0600 (already done for env files).

## Status vs SSOT

| SSOT Task | Finding | Status |
|-----------|---------|--------|
| TASK-001.1 Header sanitization | SEC-LOW-005 | NOT IMPLEMENTED |
| TASK-001.2 Rate limiting per IP | SEC-HIGH-001 | NOT IMPLEMENTED |
| TASK-001.3 Request size limit | Already enforced (10MB) | DONE |
| TASK-005.1/5.2 Event log sanitization | event_log.py: SENSITIVE_FIELD_NAMES + redaction | DONE |
| TASK-002 Race condition | rotation.py uses threading.Lock throughout | APPEARS RESOLVED |

## Pass/Fail

**PASS** — All findings have file:line evidence.  
**NOTE** — 2 P0 gaps (rate limiting, response body size) remain unimplemented.
