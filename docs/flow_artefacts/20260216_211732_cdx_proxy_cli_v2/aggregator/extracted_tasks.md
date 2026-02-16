# Extracted Tasks — P0-P2

> Run ID: run_20260216_211732_cdx_proxy_cli_v2
> Generated: 2026-02-16T21:33:00Z
> Source: Combined Expert Report

This document contains all P0-P2 tasks extracted from the expert reports, normalized for implementation.

---

## P0 Tasks (Critical) — 7 Tasks

### P0-001: Remove access tokens from health_snapshot response
- **Source**: SS-001 (Security Sentinel)
- **File**: `src/cdx_proxy_cli_v2/health_snapshot.py:74`
- **Problem**: `entry["access_token"] = auth.token` includes full token in response
- **Fix**: Remove the line or only include token hash for identification
- **Verification**: `rg "access_token.*=.*token" src/` returns no results
- **Story Points**: 1

### P0-002: Add token sanitization to EventLogger
- **Source**: SS-002 (Security Sentinel)
- **File**: `src/cdx_proxy_cli_v2/observability/event_log.py`
- **Problem**: Event logs could inadvertently include tokens
- **Fix**: Add explicit token exclusion in `EventLogger.write()` method
- **Verification**: `rg "token\|password\|secret" src/cdx_proxy_cli_v2/observability/event_log.py` shows sanitization
- **Story Points**: 2

### P0-003: Implement HTTP connection pooling
- **Source**: PE-001 (Performance Engineer)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py:274-276`
- **Problem**: New connection created for every request
- **Fix**: Use urllib3.PoolManager or maintain connection pool per host
- **Verification**: Benchmark shows <50ms p99 latency for 100 requests
- **Story Points**: 5

### P0-004: Create proxy server unit tests
- **Source**: TE-001 (Testability Expert)
- **File**: New file `tests/proxy/test_server.py`
- **Problem**: 488-line server module has zero tests
- **Fix**: Create tests for routing, auth injection, streaming, retry logic
- **Verification**: `pytest tests/proxy/test_server.py -v` runs 20+ tests
- **Story Points**: 8

### P0-005: Create config settings unit tests
- **Source**: TE-002 (Testability Expert)
- **File**: New file `tests/config/test_settings.py`
- **Problem**: Complex precedence logic untested
- **Fix**: Test CLI > env > file > default precedence
- **Verification**: `pytest tests/config/test_settings.py -v` runs 15+ tests
- **Story Points**: 3

### P0-006: Refactor server.py into focused modules
- **Source**: MG-001 (Maintainability Guardian)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py`
- **Problem**: God-class with 488 lines
- **Fix**: Extract ProxyRuntime, ProxyHandler, management endpoints, streaming
- **Verification**: Each file under 200 lines; tests pass
- **Story Points**: 8

### P0-007: Standardize error output destination
- **Source**: AC-001 (API Curator)
- **File**: `src/cdx_proxy_cli_v2/cli/main.py`
- **Problem**: Some errors to stdout, some to stderr
- **Fix**: All errors → stderr, all data → stdout, add --quiet flag
- **Verification**: `cdx2 invalid-command 2>/dev/null` produces no output
- **Story Points**: 2

---

## P1 Tasks (High) — 17 Tasks

### P1-001: Add rate limiting to management endpoints
- **Source**: SS-003 (Security Sentinel)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py:180-187`
- **Story Points**: 5

### P1-002: Add JWT decoding security warning
- **Source**: SS-005 (Security Sentinel)
- **File**: `src/cdx_proxy_cli_v2/limits_domain.py:26-38`
- **Story Points**: 1

### P1-003: Wrap trace store event IDs
- **Source**: PE-002 (Performance Engineer)
- **File**: `src/cdx_proxy_cli_v2/observability/trace_store.py:21-22`
- **Story Points**: 1

### P1-004: Make event log writes async/buffered
- **Source**: PE-004 (Performance Engineer)
- **File**: `src/cdx_proxy_cli_v2/observability/event_log.py:43-49`
- **Story Points**: 3

### P1-005: Create runtime service tests
- **Source**: TE-003 (Testability Expert)
- **File**: New file `tests/runtime/test_service.py`
- **Story Points**: 5

### P1-006: Create HTTP client tests
- **Source**: TE-004 (Testability Expert)
- **File**: New file `tests/proxy/test_http_client.py`
- **Story Points**: 2

### P1-007: Inject time provider for testability
- **Source**: TE-005 (Testability Expert)
- **File**: `src/cdx_proxy_cli_v2/auth/rotation.py`
- **Story Points**: 3

### P1-008: Standardize error handling patterns
- **Source**: MG-003 (Maintainability Guardian)
- **File**: Multiple
- **Story Points**: 5

### P1-009: Add docstrings to public functions
- **Source**: MG-004 (Maintainability Guardian)
- **File**: `src/cdx_proxy_cli_v2/auth/rotation.py` and others
- **Story Points**: 3

### P1-010: Extract magic numbers to constants
- **Source**: MG-005 (Maintainability Guardian)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py:235` and others
- **Story Points**: 2

### P1-011: Add --show-config command
- **Source**: SA-002 (Simplicity Architect)
- **File**: `src/cdx_proxy_cli_v2/cli/main.py`
- **Story Points**: 2

### P1-012: Document AuthState state machine
- **Source**: SA-003 (Simplicity Architect)
- **File**: `src/cdx_proxy_cli_v2/auth/models.py`
- **Story Points**: 2

### P1-013: Extract _proxy_request into focused methods
- **Source**: SA-004 (Simplicity Architect)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py:236-340`
- **Story Points**: 5

### P1-014: Standardize JSON output format
- **Source**: AC-002 (API Curator)
- **File**: `src/cdx_proxy_cli_v2/cli/main.py`
- **Story Points**: 3

### P1-015: Document exit codes
- **Source**: AC-003 (API Curator)
- **File**: `src/cdx_proxy_cli_v2/cli/main.py`, README.md
- **Story Points**: 1

### P1-016: Add --log-format=json option
- **Source**: AC-004 (API Curator)
- **File**: `src/cdx_proxy_cli_v2/cli/main.py`
- **Story Points**: 3

### P1-017: Extract CLI business logic to services
- **Source**: MG-002 (Maintainability Guardian)
- **File**: `src/cdx_proxy_cli_v2/cli/main.py`
- **Story Points**: 8

---

## P2 Tasks (Medium) — 15 Tasks

### P2-001: Use shlex.quote for shell exports
- **Source**: SS-006 (Security Sentinel)
- **Story Points**: 1

### P2-002: Add security headers to management responses
- **Source**: SS-008 (Security Sentinel)
- **Story Points**: 2

### P2-003: Reduce TUI default polling interval
- **Source**: PE-005 (Performance Engineer)
- **Story Points**: 1

### P2-004: Reduce auth pool lock contention
- **Source**: PE-007 (Performance Engineer)
- **Story Points**: 3

### P2-005: Create CLI integration tests
- **Source**: TE-006 (Testability Expert)
- **Story Points**: 5

### P2-006: Add shared fixtures to conftest.py
- **Source**: TE-007 (Testability Expert)
- **Story Points**: 2

### P2-007: Add max_iterations to TUI for testing
- **Source**: TE-008 (Testability Expert)
- **Story Points**: 1

### P2-008: Consolidate timestamp utilities
- **Source**: MG-006 (Maintainability Guardian)
- **Story Points**: 2

### P2-009: Document AuthState thread safety
- **Source**: MG-008 (Maintainability Guardian)
- **Story Points**: 1

### P2-010: Document proxy startup architecture
- **Source**: SA-007 (Simplicity Architect)
- **Story Points**: 1

### P2-011: Standardize management endpoint paths
- **Source**: AC-005 (API Curator)
- **Story Points**: 3

### P2-012: Document health vs doctor usage
- **Source**: AC-007 (API Curator)
- **Story Points**: 1

### P2-013: Add log sanitization
- **Source**: SS-007 (Security Sentinel)
- **Story Points**: 2

### P2-014: Document env var to CLI arg mapping
- **Source**: AC-006 (API Curator)
- **Story Points**: 1

### P2-015: Add examples to all CLI command help
- **Source**: AC-010 (API Curator)
- **Story Points**: 2

---

## Summary

| Priority | Tasks | Total Story Points |
|----------|-------|-------------------|
| P0 | 7 | 29 |
| P1 | 17 | 54 |
| P2 | 15 | 28 |
| **Total** | **39** | **111** |

## Recommended Card Groups

Cards should be generated to group related tasks:

1. **Security Hardening** (P0-001, P0-002, P1-001, P2-001, P2-002, P2-013)
2. **Connection Pooling** (P0-003)
3. **Test Coverage** (P0-004, P0-005, P1-005, P1-006, P2-005, P2-006, P2-007)
4. **Server Refactoring** (P0-006, P1-013)
5. **CLI Improvements** (P0-007, P1-011, P1-014, P1-015, P1-016, P1-017, P2-014, P2-015)
6. **API Consistency** (P1-012, P2-011, P2-012)
7. **Performance** (P1-003, P1-004, P2-003, P2-004)
8. **Code Quality** (P1-007, P1-008, P1-009, P1-010, P2-008, P2-009, P2-010)
