# CARD-009 — Add pagination to /trace endpoint

**Priority:** P1  
**Complexity:** 1h  
**Source Finding:** F-P1-007

## Context

`/trace` returns all events (up to `trace_max`, default 500) in one response. No pagination support makes large trace dumps slow.

## Goal

Add `?limit=N&offset=M` query parameters to the `/trace` management route.

## Acceptance Criteria

1. `?limit=50` returns the last 50 events (default when no limit specified: 50).
2. `?offset=50&limit=50` returns events 50-100 from the end.
3. Response includes `{"events": [...], "total": N, "limit": M, "offset": K}` envelope.
4. Old clients sending no parameters get first 50 events (not 500).
5. Unit test: assert pagination boundaries are correct.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/server.py` (trace handler)
- `tests/proxy/test_server.py`
