# CARD-006: Add auth record caching with TTL

## Metadata

| Field | Value |
|-------|-------|
| ID | CARD-006 |
| Priority | P1 |
| Complexity | 2 hours |
| Status | draft |
| Blocked by | — |

## Context

**Source Finding**: P1-002 (Performance Report)

**Problem**: Auth files are parsed from disk on every health check with no caching.

**File**: `src/cdx_proxy_cli_v2/auth/store.py:44-47`

## Goal

Add a simple TTL-based cache for auth record loading.

## Acceptance Criteria

- [ ] Add `AuthCache` class with TTL support
- [ ] Default TTL: 30 seconds
- [ ] Cache invalidated on explicit reload
- [ ] Add `--auth-cache-ttl` CLI flag
- [ ] Add cache hit/miss metrics to debug endpoint
- [ ] Tests for cache behavior

## Implementation Notes

```python
# auth/store.py
import time
from typing import Optional

class AuthCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self._ttl = ttl_seconds
        self._cache: Optional[List[AuthRecord]] = None
        self._cached_at: float = 0.0
        self._hits = 0
        self._misses = 0
    
    def get(self, loader: Callable[[], List[AuthRecord]]) -> List[AuthRecord]:
        now = time.time()
        if self._cache is not None and (now - self._cached_at) < self._ttl:
            self._hits += 1
            return self._cache
        self._misses += 1
        self._cache = loader()
        self._cached_at = now
        return self._cache
    
    def invalidate(self) -> None:
        self._cache = None
        self._cached_at = 0.0
```

## Definition of Done

- [ ] Cache implemented with TTL
- [ ] CLI flag added
- [ ] Metrics available
- [ ] Tests pass
