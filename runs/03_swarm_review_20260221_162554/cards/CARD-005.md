# CARD-005: Make request body size configurable

## Metadata

| Field | Value |
|-------|-------|
| ID | CARD-005 |
| Priority | P1 |
| Complexity | 1 hour |
| Status | draft |
| Blocked by | — |

## Context

**Source Finding**: P1-001 (Security Report)

**Problem**: Request body size limit is hardcoded to 10MB. This could be a DoS vector for memory-constrained environments.

**File**: `src/cdx_proxy_cli_v2/proxy/server.py:17-18`

## Goal

Make request and response body size limits configurable via CLI flags.

## Acceptance Criteria

- [ ] Add `--max-request-body` CLI flag (default: 10MB)
- [ ] Add `--max-response-body` CLI flag (default: 10MB)
- [ ] Add corresponding env variables
- [ ] Update `Settings` dataclass with new fields
- [ ] Document new options in README

## Implementation Notes

```python
# config/settings.py
DEFAULT_MAX_REQUEST_BODY = 10 * 1024 * 1024  # 10MB
DEFAULT_MAX_RESPONSE_BODY = 10 * 1024 * 1024  # 10MB

ENV_MAX_REQUEST_BODY = "CLIPROXY_MAX_REQUEST_BODY"
ENV_MAX_RESPONSE_BODY = "CLIPROXY_MAX_RESPONSE_BODY"

@dataclass(frozen=True)
class Settings:
    # ... existing fields ...
    max_request_body: int
    max_response_body: int

# proxy/server.py
class ProxyHandler:
    def _read_body(self) -> Optional[bytes]:
        # ... 
        if length > self.server.runtime.settings.max_request_body:
            self._send_json(413, {"error": "request body too large"})
            return None
```

## Definition of Done

- [ ] CLI flags implemented
- [ ] Env variables supported
- [ ] Default behavior unchanged
- [ ] Documentation updated
