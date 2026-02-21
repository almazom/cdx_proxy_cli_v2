# Simplicity Expert Report — cdx_proxy_cli_v2

**Run:** 03_swarm_review_20260221_125112  
**Role:** Simplicity  
**Analyst:** strategy_variation_simplicity  
**Date:** 2026-02-21

## Summary

The proxy is conceptually simple (intercept → auth-inject → forward) but the implementation complexity has grown beyond what the feature set requires. Key areas: settings resolution chain, header filtering logic, and the auth pool state machine have more states than necessary.

## Findings

### SIMP-MED-001 — `build_forward_headers()` has implicit dual-mode logic that's hard to reason about

**File:** `src/cdx_proxy_cli_v2/proxy/rules.py:89-110`  
**Evidence:**
```python
if chatgpt_responses_mode and (normalized in CHATGPT_RESPONSES_DROP_HEADERS or "_" in key):
    continue
if chatgpt_responses_mode:
    if normalized in allowed_chatgpt_headers or normalized.startswith("x-openai-") ...:
        headers[key] = value
    continue
headers[key] = value
```
Two separate `if chatgpt_responses_mode:` branches in a single loop are confusing. The allowlist/denylist interaction requires careful reading to understand precedence.

**Priority:** P2  
**Recommendation:** Restructure as explicit `if chatgpt_responses_mode: return _build_chatgpt_headers(...)` vs generic path. Separate functions, each testable independently.

---

### SIMP-MED-002 — `build_settings()` merges 4 config layers manually

**File:** `src/cdx_proxy_cli_v2/config/settings.py:195-245`  
**Evidence:** Manual merge: `merged = dict(file_env); merged.update(os.environ)` then individual field resolution with 4 layers.

This pattern is error-prone and hard to extend. Adding a new setting requires updating `build_settings`, `Settings` dataclass, env var constants, and env file parsing.

**Priority:** P2  
**Recommendation:** Use a typed settings library (pydantic or a simple descriptor pattern) that handles layer merging automatically.

---

### SIMP-LOW-003 — `AuthState.status()` and `AuthState.available()` have overlapping logic

**File:** `src/cdx_proxy_cli_v2/auth/models.py:35-50`  
**Evidence:** Both methods check `blacklist_until`, `cooldown_until`, `probation_successes`. Logic is duplicated with slight variations.

**Priority:** P2  
**Recommendation:** `available()` should call `status()` rather than duplicating checks.

---

### SIMP-LOW-004 — `_proxy_request()` retries with a while loop but max_attempts equals auth count

**File:** `src/cdx_proxy_cli_v2/proxy/server.py:323-335`  
**Evidence:**
```python
max_attempts = max(1, runtime.auth_pool.count())
attempt = 0
while attempt < max_attempts:
```
This means with 10 auth files, a single failed request triggers up to 10 upstream calls. The retry semantics are not documented.

**Priority:** P2  
**Recommendation:** Document retry policy; consider separating "max auth attempts" from "max upstream retries" as distinct concepts.

## Pass/Fail

**PASS** — All findings have file:line evidence.
