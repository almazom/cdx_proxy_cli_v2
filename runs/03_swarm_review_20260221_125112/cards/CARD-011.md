# CARD-011 — Refactor build_forward_headers() into separate chatgpt/generic paths

**Priority:** P2  
**Complexity:** 1h  
**Source Finding:** F-P2-002

## Goal

Split `build_forward_headers()` into `_build_chatgpt_response_headers()` and `_build_generic_headers()`. Caller decides which to use.

## Acceptance Criteria

1. Two private functions with clear single responsibility.
2. All existing `test_rules.py` header tests pass.
3. No behavior change.

## Files to Modify

- `src/cdx_proxy_cli_v2/proxy/rules.py`
- `tests/proxy/test_rules.py`
