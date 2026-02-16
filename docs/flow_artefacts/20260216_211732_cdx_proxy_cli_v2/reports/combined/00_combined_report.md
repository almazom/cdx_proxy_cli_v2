# Combined Expert Report — cdx_proxy_cli_v2

> Run ID: run_20260216_211732_cdx_proxy_cli_v2
> Generated: 2026-02-16T21:32:00Z
> Experts: 6 (Maintainability Guardian, Simplicity Architect, Testability Expert, Security Sentinel, Performance Engineer, API Curator)

## Summary Statistics

| Priority | Count | Description |
|----------|-------|-------------|
| P0 | 7 | Critical — Must fix immediately |
| P1 | 17 | High — Should fix this sprint |
| P2 | 15 | Medium — Should fix soon |
| P3 | 12 | Low — Nice to have |
| **Total** | **51** | |

---

## P0 (Critical) — Must Fix Immediately

### Security

| ID | Title | Evidence | Recommendation |
|----|-------|----------|----------------|
| SS-001 | Access tokens leaked in collective_health_snapshot response | `src/cdx_proxy_cli_v2/health_snapshot.py:74` | Never include tokens in response payloads |
| SS-002 | Tokens potentially written to event log | `src/cdx_proxy_cli_v2/proxy/server.py:172` | Add explicit token exclusion in EventLogger |

### Performance

| ID | Title | Evidence | Recommendation |
|----|-------|----------|----------------|
| PE-001 | No HTTP connection pooling to upstream | `src/cdx_proxy_cli_v2/proxy/server.py:274-276` | Implement connection pooling with urllib3 |

### Testability

| ID | Title | Evidence | Recommendation |
|----|-------|----------|----------------|
| TE-001 | Zero test coverage for proxy server module | No `tests/proxy/test_server.py` | Create comprehensive server tests |
| TE-002 | Config settings merging logic untested | No `tests/config/test_settings.py` | Test precedence rules |

### Maintainability

| ID | Title | Evidence | Recommendation |
|----|-------|----------|----------------|
| MG-001 | Server.py has god-class symptoms | `src/cdx_proxy_cli_v2/proxy/server.py:1-488` | Extract into separate modules |
| MG-002 | CLI main.py mixes parsing, logic, presentation | `src/cdx_proxy_cli_v2/cli/main.py:85-424` | Extract business logic to services |

### API

| ID | Title | Evidence | Recommendation |
|----|-------|----------|----------------|
| AC-001 | Inconsistent error output destination | `src/cdx_proxy_cli_v2/cli/main.py:102-103,90,430` | Standardize: errors → stderr, data → stdout |

---

## P1 (High) — Should Fix This Sprint

### Security

| ID | Title | Evidence |
|----|-------|----------|
| SS-003 | No rate limiting on management endpoint | `src/cdx_proxy_cli_v2/proxy/server.py:180-187` |
| SS-004 | Management key stored in plaintext | `src/cdx_proxy_cli_v2/config/settings.py:181-186` |
| SS-005 | JWT decoding without signature verification warning | `src/cdx_proxy_cli_v2/limits_domain.py:26-38` |

### Performance

| ID | Title | Evidence |
|----|-------|----------|
| PE-002 | Trace store event IDs unbounded | `src/cdx_proxy_cli_v2/observability/trace_store.py:21-22` |
| PE-004 | Event log writes are synchronous | `src/cdx_proxy_cli_v2/observability/event_log.py:43-49` |

### Testability

| ID | Title | Evidence |
|----|-------|----------|
| TE-003 | Runtime service lifecycle untested | No `tests/runtime/test_service.py` |
| TE-004 | HTTP client has no error path tests | No `tests/proxy/test_http_client.py` |
| TE-005 | Time-dependent tests use monkeypatch | `tests/auth/test_rotation.py:22-71` |

### Maintainability

| ID | Title | Evidence |
|----|-------|----------|
| MG-003 | Inconsistent return type patterns | Multiple files with different error handling |
| MG-004 | Missing docstrings on public functions | `src/cdx_proxy_cli_v2/auth/rotation.py:22-189` |
| MG-005 | Magic numbers without constants | `src/cdx_proxy_cli_v2/proxy/server.py:235` |

### Simplicity

| ID | Title | Evidence |
|----|-------|----------|
| SA-002 | Configuration resolution too many fallbacks | `src/cdx_proxy_cli_v2/config/settings.py:135-185` |
| SA-003 | AuthState state machine is implicit | `src/cdx_proxy_cli_v2/auth/models.py:38-48` |
| SA-004 | _proxy_request method does too much | `src/cdx_proxy_cli_v2/proxy/server.py:236-340` |

### API

| ID | Title | Evidence |
|----|-------|----------|
| AC-002 | JSON output format inconsistent | Different structures for doctor vs all |
| AC-003 | Exit codes not documented | Mixed return values in main.py |
| AC-004 | No structured logging format option | Mixed print() and JSONL |

---

## P2 (Medium) — Should Fix Soon

### Security

| ID | Title |
|----|-------|
| SS-006 | Shell export escaping may be insufficient |
| SS-007 | Log files may contain sensitive data |
| SS-008 | No security headers on responses |

### Performance

| ID | Title |
|----|-------|
| PE-005 | TUI polling interval creates visible lag |
| PE-006 | Repeated string operations in path rewriting |
| PE-007 | Auth pool holds lock during pick |

### Testability

| ID | Title |
|----|-------|
| TE-006 | No integration tests for CLI commands |
| TE-007 | Test fixtures not defined in conftest.py |
| TE-008 | TUI untestable due to infinite loop |

### Maintainability

| ID | Title |
|----|-------|
| MG-006 | Duplicated timestamp formatting |
| MG-007 | Inconsistent naming conventions |
| MG-008 | AuthState mutable in thread-safe context |

### Simplicity

| ID | Title |
|----|-------|
| SA-005 | Collective dashboard excessive formatting functions |
| SA-006 | TUI polling loop could use asyncio |
| SA-007 | Multiple ways to start proxy |

### API

| ID | Title |
|----|-------|
| AC-005 | Management endpoint paths inconsistent |
| AC-006 | CLI argument naming inconsistent |
| AC-007 | Health endpoint structure differs from doctor |

---

## P3 (Low) — Nice to Have

| Area | Count | Examples |
|------|-------|----------|
| Maintainability | 2 | Empty `__init__.py` files, long parameter lists |
| Simplicity | 2 | Box drawing inline, shutdown handling |
| Testability | 2 | Missing coverage metrics, event log tests |
| Security | 2 | Dependency security, no SECURITY.md |
| Performance | 3 | No metrics, settings caching, rich rendering |
| API | 3 | No API version, no pagination, help discoverability |

---

## Prioritized Action Plan

### Sprint 1 (Week 1-2) — P0 Items

1. **SS-001**: Remove token from health_snapshot response
2. **SS-002**: Add token sanitization to EventLogger
3. **TE-001**: Create tests/proxy/test_server.py
4. **TE-002**: Create tests/config/test_settings.py
5. **MG-001**: Begin server.py refactoring
6. **AC-001**: Standardize error output

### Sprint 2 (Week 3-4) — P1 Items

1. **SA-001**: Implement connection pooling
2. **SS-003**: Add rate limiting to management endpoints
3. **TE-003/004**: Add service and HTTP client tests
4. **SA-004**: Refactor _proxy_request method
5. **AC-002/003**: Standardize JSON and exit codes

### Backlog — P2/P3 Items

Address incrementally based on team capacity and user feedback.

---

## Confidence Scores by Expert

| Expert | Confidence |
|--------|------------|
| Maintainability Guardian | 85% |
| Simplicity Architect | 80% |
| Testability Expert | 90% |
| Security Sentinel | 85% |
| Performance Engineer | 80% |
| API Curator | 85% |
| **Average** | **84%** |
