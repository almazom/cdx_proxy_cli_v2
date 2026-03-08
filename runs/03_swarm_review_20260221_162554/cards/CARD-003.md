# CARD-003: Add API versioning (/v1/ prefix)

## Metadata

| Field | Value |
|-------|-------|
| ID | CARD-003 |
| Priority | P0 |
| Complexity | 2 hours |
| Status | draft |
| Blocked by | — |

## Context

**Source Finding**: P0-003 (API Report)

**Problem**: Management endpoints have no version prefix. Breaking changes will affect all clients.

**File**: `src/cdx_proxy_cli_v2/proxy/server.py:175-205`

## Goal

Add `/v1/` prefix to all management endpoints for future API versioning support.

## Acceptance Criteria

- [ ] Add `/v1/debug`, `/v1/trace`, `/v1/health`, `/v1/auth-files`, `/v1/shutdown`, `/v1/reset`
- [ ] Keep legacy endpoints as aliases (backward compatibility)
- [ ] Update `management_route()` function in `rules.py`
- [ ] Update CLI to use new endpoints
- [ ] Document API version in `/v1/debug` response
- [ ] Add deprecation notice for legacy endpoints (log warning)

## Implementation Notes

```python
# proxy/rules.py
def management_route(path: str) -> Optional[str]:
    path_only = urlsplit(path or "").path
    
    # New versioned routes (preferred)
    versioned_routes = {
        "/v1/debug": "debug",
        "/v1/trace": "trace",
        "/v1/health": "health",
        "/v1/auth-files": "auth-files",
        "/v1/shutdown": "shutdown",
        "/v1/reset": "reset",
    }
    if path_only in versioned_routes:
        return versioned_routes[path_only]
    
    # Legacy routes (deprecated but supported)
    legacy_routes = {
        "/debug": "debug",
        "/trace": "trace",
        "/health": "health",
        "/auth-files": "auth-files",
        "/shutdown": "shutdown",
        "/reset": "reset",
    }
    if path_only in legacy_routes:
        # Log deprecation warning
        return legacy_routes[path_only]
    
    return None
```

## Testing

1. Test new `/v1/*` endpoints work
2. Test legacy endpoints still work
3. Verify deprecation warnings logged for legacy

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Breaking existing clients | Keep legacy routes working |
| Confusion about which to use | Document preferred routes |

## Definition of Done

- [ ] New versioned endpoints implemented
- [ ] Legacy backward compatibility maintained
- [ ] Tests for both old and new routes
- [ ] Documentation updated
