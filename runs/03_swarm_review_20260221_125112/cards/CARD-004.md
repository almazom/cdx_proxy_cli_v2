# CARD-004 — Fix EventLogger: persistent handle + NullEventLogger for tests

**Priority:** P1  
**Complexity:** 2h  
**Source Finding:** F-P1-002

## Context

`event_log.py:62-67` opens and closes the JSONL file on every `write()` call. At 100 req/s this is a significant I/O bottleneck.

## Goal

Keep a persistent file handle opened once at startup. Flush after each write. Add `NullEventLogger` for test isolation.

## Acceptance Criteria

1. `EventLogger` opens the file handle in `__init__()` (or on first write via lazy init).
2. File handle remains open; `write()` just appends and flushes.
3. `EventLogger.close()` method added (and called on server shutdown).
4. `NullEventLogger` stub (same interface, no I/O) added for use in tests.
5. All existing `test_event_log_sanitization.py` tests pass.
6. No file handle leak: handle closed on `__del__` or context manager exit.

## Files to Modify

- `src/cdx_proxy_cli_v2/observability/event_log.py`
- `tests/observability/test_event_log_sanitization.py` (update to use NullEventLogger where needed)
