# CARD-008 — Add concurrent stress test for auth rotation

**Priority:** P1  
**Complexity:** 2h  
**Source Finding:** F-P1-006  
**SSOT Ref:** TASK-002.3

## Context

TASK-002 (race condition fix) was reportedly completed but no concurrent stress test exists to verify the fix under real parallel load.

## Goal

Add a concurrent stress test that verifies `RoundRobinAuthPool` is safe under 10 concurrent threads.

## Acceptance Criteria

1. Test: 10 threads each call `pool.pick()` + `pool.mark_result(status=429)` 100 times concurrently.
2. Assert: no exception raised; final pool state is self-consistent (no negative counters, etc.).
3. Test: 5 threads call `pool.pick()` + `pool.mark_result(status=200)` while 5 others call `mark_result(status=401)` → assert blacklisted count is accurate.
4. Test completes in < 5s.

## Files to Modify

- `tests/auth/test_rotation.py`
