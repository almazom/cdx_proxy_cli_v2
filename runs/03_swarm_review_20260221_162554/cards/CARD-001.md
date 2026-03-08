# CARD-001: Implement HTTP connection pooling

## Metadata

| Field | Value |
|-------|-------|
| ID | CARD-001 |
| Priority | P0 |
| Complexity | 3 hours |
| Status | draft |
| Blocked by | — |

## Context

**Source Finding**: P0-001 (Performance Report)

**Problem**: Currently, the proxy creates a new `HTTPConnection` for each upstream request. This adds 50-200ms latency per request due to TCP and TLS handshake overhead.

**File**: `src/cdx_proxy_cli_v2/proxy/server.py:210-240`

## Goal

Implement HTTP connection pooling to reuse connections across requests, reducing latency.

## Acceptance Criteria

- [ ] Add `urllib3` as a dependency in `pyproject.toml`
- [ ] Create `ConnectionPool` class or use `urllib3.PoolManager`
- [ ] Integrate pool into `ProxyHandler._proxy_request()`
- [ ] Configure pool size (default: 10 connections)
- [ ] Add pool configuration via CLI flag `--pool-size`
- [ ] Add tests for connection reuse
- [ ] Document new flag in README

## Implementation Notes

```python
# Example integration pattern
from urllib3 import PoolManager

class ProxyRuntime:
    def __post_init__(self):
        self._pool = PoolManager(maxsize=10)
        
# In _proxy_request:
response = runtime._pool.request(
    method=self.command,
    url=f"{scheme}://{host}:{port}{full_path}",
    body=body,
    headers=headers,
    timeout=timeout,
)
```

## Testing

1. Unit test: Mock PoolManager, verify reuse
2. Integration test: Measure latency improvement
3. Load test: Verify pool doesn't leak connections

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Connection leaks | Add explicit cleanup in finally block |
| Pool exhaustion | Configure appropriate maxsize |
| Breaking change | Keep current behavior as fallback |

## Definition of Done

- [ ] Code implemented and reviewed
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Documentation updated
- [ ] No regressions in existing tests
