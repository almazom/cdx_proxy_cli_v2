# CARD-010 — Remove /debug filesystem path leakage

**Priority:** P2  
**Complexity:** 1h  
**Source Finding:** F-P2-005  
**SSOT Ref:** TASK-001.1 (partial)

## Goal

Remove `auth_dir` and `event_log_file` from default `/v1/debug` response. Add `?verbose=true` to opt-in to full details.

## Acceptance Criteria

1. Default `/v1/debug` response omits `auth_dir` and `event_log_file`.
2. `/v1/debug?verbose=true` (management key required) returns full payload including filesystem paths.
3. Tests updated.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/server.py` (`debug_payload`)
