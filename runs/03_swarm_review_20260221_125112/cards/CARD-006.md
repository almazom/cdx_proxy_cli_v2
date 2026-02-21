# CARD-006 — Add Settings schema validation

**Priority:** P1  
**Complexity:** 2h  
**Source Finding:** F-P1-004  
**SSOT Ref:** TASK-004

## Context

`build_settings()` merges 3 config layers but performs no validation. Invalid values (empty host, negative ports, etc.) silently fall through to defaults or cause runtime errors.

## Goal

Add a `validate_settings()` function that checks all fields and logs warnings on startup.

## Acceptance Criteria

1. `validate_settings(settings: Settings) -> list[str]` returns a list of warning strings (empty = valid).
2. Checks: `port` in 1-65535, `upstream` is a valid URL, `trace_max` > 0, `compact_timeout` > 0.
3. On startup, `build_settings()` calls `validate_settings()` and logs each warning via `EventLogger`.
4. Unit tests for each validation rule.
5. Existing settings tests pass.

## Files to Modify

- `src/cdx_proxy_cli_v2/config/settings.py`
- `tests/config/test_settings.py`
