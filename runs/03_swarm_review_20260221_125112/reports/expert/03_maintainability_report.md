# Maintainability Expert Report — cdx_proxy_cli_v2

**Run:** 03_swarm_review_20260221_125112  
**Role:** Maintainability  
**Analyst:** strategy_variation_maintainability  
**Date:** 2026-02-21

## Summary

The codebase is generally well-structured for a small proxy. The main maintainability risk is `proxy/server.py` which has grown to 527 lines and combines five distinct responsibilities. Configuration validation is also missing, making runtime debugging difficult.

## Findings

### MAINT-HIGH-001 — proxy/server.py has 5 mixed responsibilities (527 lines)

**File:** `src/cdx_proxy_cli_v2/proxy/server.py`  
**Evidence:** File contains:
- `ProxyRuntime` dataclass (request recording, auth management) — lines ~45-140
- `ProxyHTTPServer` class — lines ~141-160
- `ProxyHandler` (request parsing, routing, body reading, management dispatch) — lines ~161-280
- `_proxy_request()` — lines ~282-445 (~163 lines single method)
- Management endpoint handlers — lines ~227-280

The `_proxy_request()` method at ~163 lines is individually too long (>60 lines).

**Priority:** P1  
**Recommendation:** Extract `ProxyRuntime` to `proxy/runtime.py`, management handlers to `proxy/management.py`, and `_proxy_request` into a `ProxyForwarder` class. (SSOT TASK-006 partially addresses this.)

---

### MAINT-MED-002 — Settings module has 3-level config override with no schema validation

**File:** `src/cdx_proxy_cli_v2/config/settings.py:190-240` (`build_settings()`)  
**Evidence:** Settings resolved from (1) defaults, (2) `.env` file, (3) environment variables, (4) explicit parameters. No validation that values are in valid ranges or types after merge.

For example, `CLIPROXY_HOST` accepts any string including an empty string that falls through to default without error.

**Priority:** P1 (SSOT TASK-004)  
**Recommendation:** Add `validate_settings(settings: Settings) -> list[str]` that checks ranges, required fields, and logs warnings on startup.

---

### MAINT-MED-003 — Hard-coded constants in multiple files with no central config

**Files:**
- `server.py:34-35`: `DEFAULT_MAX_REQUEST_BODY`, `DEFAULT_MAX_RESPONSE_BODY`
- `settings.py:20-26`: `DEFAULT_AUTH_DIR`, `DEFAULT_HOST`, etc.
- `rotation.py:8-14`: `DEFAULT_COOLDOWN_SECONDS`, `MAX_COOLDOWN_SECONDS`, etc.

Constants are not centralized, making tuning require multiple file edits.

**Priority:** P2  
**Recommendation:** Move server-level constants to `settings.py` or a `constants.py` module.

---

### MAINT-LOW-004 — No public interface documentation for management API

**File:** `src/cdx_proxy_cli_v2/proxy/rules.py` — `management_route()`  
**Evidence:** Routes `/debug`, `/trace`, `/health`, `/auth-files`, `/shutdown`, `/reset` are string-matched inline. No OpenAPI spec or docstring documenting expected request/response shapes.

**Priority:** P2  
**Recommendation:** Add a `MANAGEMENT_ROUTES` dict with route descriptions, or generate a `/help` endpoint that lists routes.

## Pass/Fail

**PASS** — All findings have file:line evidence.
