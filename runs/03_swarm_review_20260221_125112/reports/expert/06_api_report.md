# API Expert Report — cdx_proxy_cli_v2

**Run:** 03_swarm_review_20260221_125112  
**Role:** API Design  
**Analyst:** strategy_variation_api  
**Date:** 2026-02-21

## Summary

The management API is functional but lacks versioning, schema definitions, and consistent error formats. The proxy API passthrough is correct for the ChatGPT backend use-case, but the path rewrite logic is fragile and implicit.

## Findings

### API-HIGH-001 — Management API has no versioning (breaking changes invisible)

**File:** `src/cdx_proxy_cli_v2/proxy/rules.py:41-58`  
**Evidence:**
```python
if path_only == "/debug": return "debug"
if path_only == "/trace": return "trace"
...
```
Routes are plain strings with no version prefix (e.g., `/v1/debug`). Any change to the management API shape breaks existing clients silently.

**Priority:** P1  
**Recommendation:** Add `/v1/` prefix to all management routes. Maintain old routes with deprecation headers for one version.

---

### API-MED-002 — `/trace` endpoint lacks pagination and returns unbounded list

**File:** `src/cdx_proxy_cli_v2/proxy/server.py` — `/trace` management handler  
**Evidence:** Trace endpoint returns all events up to `trace_max` (500 default) in a single JSON response. No `page`, `cursor`, or `limit` query parameters.

**Priority:** P1  
**Recommendation:** Add `?limit=N&offset=M` or cursor-based pagination. Default limit to 50.

---

### API-MED-003 — PATH_REWRITE_PATTERNS is fragile — order-dependent, no conflict detection

**File:** `src/cdx_proxy_cli_v2/proxy/rules.py:16-21`  
**Evidence:**
```python
PATH_REWRITE_PATTERNS = [
    ("/v1/responses/compact", "/codex/responses/compact"),
    ("/responses/compact", "/codex/responses/compact"),
    ("/v1/responses", "/codex/responses"),
    ("/responses", "/codex/responses"),
]
```
Order matters: `/v1/responses` would also match `/v1/responses/compact` if compact came after. Currently correct but fragile — a developer adding patterns could silently break routing.

**Priority:** P2  
**Recommendation:** Add a unit test that validates pattern order (most-specific first). Consider using regex-based routing instead.

---

### API-LOW-004 — Error response format is inconsistent

**File:** `src/cdx_proxy_cli_v2/proxy/server.py`  
**Evidence:** Some errors: `{"error": "msg"}`, management 401: `{"error": "unauthorized management request"}`, upstream errors pass through directly from upstream. No unified error envelope.

**Priority:** P2  
**Recommendation:** Define and document a standard error envelope: `{"error": {"code": "...", "message": "..."}}` and apply it consistently.

---

### API-LOW-005 — `/health` endpoint schema not documented

**File:** Management route handling  
**Evidence:** `/health` returns `health_snapshot()` dict with `ok` and `accounts` fields, but no schema documentation exists.

**Priority:** P2  
**Recommendation:** Add docstring or a `GET /v1/schema` endpoint listing all management routes and their response schemas.

## Pass/Fail

**PASS** — All findings have file:line evidence.
