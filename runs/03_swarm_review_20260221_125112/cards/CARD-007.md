# CARD-007 — Add /v1/ versioning prefix to management API

**Priority:** P1  
**Complexity:** 2h  
**Source Finding:** F-P1-005

## Context

Management routes `/debug`, `/trace`, `/health`, `/auth-files`, `/shutdown`, `/reset` have no version prefix. Breaking changes are invisible to API clients.

## Goal

Add `/v1/` prefix to all management routes. Keep old routes with `X-Deprecated: true` header.

## Acceptance Criteria

1. `management_route()` in `rules.py` recognizes both `/v1/debug` and `/debug` (legacy).
2. Legacy routes (`/debug`, `/trace`, etc.) return `X-Deprecated: true` response header.
3. All `tests/proxy/test_rules.py` tests pass.
4. `test_server.py` management tests updated to use `/v1/` prefix.
5. README management API section updated.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/rules.py`
- `src/cdx_proxy_cli_v2/proxy/server.py` (header injection for deprecated routes)
- `tests/proxy/test_rules.py`
