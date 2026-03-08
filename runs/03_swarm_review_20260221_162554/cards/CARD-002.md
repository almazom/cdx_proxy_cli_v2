# CARD-002: Extract ProxyLogic class for testability

## Metadata

| Field | Value |
|-------|-------|
| ID | CARD-002 |
| Priority | P0 |
| Complexity | 4 hours |
| Status | draft |
| Blocked by | — |

## Context

**Source Finding**: P0-002 (Testability Report)

**Problem**: `ProxyHandler` inherits from `BaseHTTPRequestHandler`, making it difficult to unit test business logic without running a full HTTP server.

**File**: `src/cdx_proxy_cli_v2/proxy/server.py:95-340`

## Goal

Extract business logic from `ProxyHandler` into a testable `ProxyLogic` class that can be instantiated and tested independently.

## Acceptance Criteria

- [ ] Create `ProxyLogic` class in `src/cdx_proxy_cli_v2/proxy/logic.py`
- [ ] Move request handling logic from `ProxyHandler` to `ProxyLogic`
- [ ] `ProxyLogic` takes runtime and request data as parameters
- [ ] `ProxyLogic` returns response data (status, headers, body)
- [ ] `ProxyHandler` delegates to `ProxyLogic`
- [ ] Add unit tests for `ProxyLogic` without HTTP mocking
- [ ] Existing integration tests continue to pass

## Implementation Notes

```python
# proxy/logic.py
@dataclass
class ProxyRequest:
    method: str
    path: str
    headers: Dict[str, str]
    body: Optional[bytes]
    client_ip: Optional[str]

@dataclass
class ProxyResponse:
    status: int
    headers: List[Tuple[str, str]]
    body: bytes
    stream_response: Optional[...] = None

class ProxyLogic:
    def __init__(self, runtime: ProxyRuntime):
        self.runtime = runtime
    
    def handle(self, request: ProxyRequest) -> ProxyResponse:
        # Business logic here
        pass

# proxy/server.py
class ProxyHandler(BaseHTTPRequestHandler):
    def _proxy_request(self):
        request = ProxyRequest(
            method=self.command,
            path=self.path,
            headers=dict(self.headers),
            body=self._read_body(),
            client_ip=self.client_address[0],
        )
        response = self.logic.handle(request)
        self._send_response(response)
```

## Testing

1. Unit test `ProxyLogic.handle()` with mock runtime
2. Test error handling paths
3. Test auth rotation logic
4. Verify no HTTP stack needed

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Breaking existing behavior | Keep existing tests passing |
| Incomplete extraction | Start with happy path, expand |

## Definition of Done

- [ ] `ProxyLogic` class implemented
- [ ] Unit tests with >90% coverage of new class
- [ ] All existing tests pass
- [ ] Code review approved
