---
expert_id: "maintainability_guardian"
expert_name: "Maintainability Guardian"
run_id: "run_20260216_211732_cdx_proxy_cli_v2"
generated_at_utc: "2026-02-16T21:20:00Z"
read_only_target_repo: true
---

# Executive Summary

- **Top Risk 1**: Large monolithic files (`server.py` at 488 lines, `main.py` at 424 lines) with mixed responsibilities making testing and maintenance difficult.
- **Top Risk 2**: Inconsistent error handling patterns across modules - some use exceptions, some return None/tuples, some use string error codes.
- **Top Risk 3**: Missing type annotations in several functions and using `Any` too liberally reduces IDE support and catches fewer bugs at development time.

# P0 (Critical) — Must Fix

## MG-001: Server.py has god-class symptoms with 488 lines handling HTTP, auth, tracing, and streaming
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:1-488` — Single file contains ProxyRuntime, ProxyHTTPServer, ProxyHandler classes plus utility functions. Handler method `_proxy_request` spans 100+ lines with nested try/except/finally blocks.
- **Impact**: High cognitive load for developers, difficult to unit test individual behaviors, high change risk.
- **Recommendation**: Extract into separate modules:
  - `proxy/runtime.py` - ProxyRuntime class
  - `proxy/handler.py` - ProxyHandler class  
  - `proxy/management.py` - Management endpoint handlers
  - `proxy/streaming.py` - SSE stream handling logic
- **Verification**: `wc -l src/cdx_proxy_cli_v2/proxy/*.py` shows each file under 200 lines; `pytest tests/proxy/` passes.

## MG-002: CLI main.py mixes argument parsing, business logic, and presentation
- **Evidence**: `src/cdx_proxy_cli_v2/cli/main.py:85-424` — `handle_doctor`, `handle_all`, `handle_proxy` contain both orchestration and business logic directly in handler functions.
- **Impact**: Cannot reuse business logic, difficult to test, tight coupling to argparse.
- **Recommendation**: Extract business logic into service classes:
  - `services/doctor_service.py` - Doctor command logic
  - `services/proxy_service.py` - Proxy command logic
  - CLI handlers should only parse args and call services
- **Verification**: `rg "def handle_" src/cdx_proxy_cli_v2/cli/main.py` shows handlers are <20 lines each.

# P1 (High)

## MG-003: Inconsistent return type patterns for error handling
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/auth/store.py:53` — `read_auth_json` returns `Tuple[Optional[Dict], Optional[str]]` (data, error_code)
  - `src/cdx_proxy_cli_v2/proxy/http_client.py:19` — `fetch_json` raises exceptions on failure
  - `src/cdx_proxy_cli_v2/runtime/service.py:91` — `_read_pid` returns `Optional[int]` silently swallowing errors
- **Impact**: Callers cannot predict error handling, leading to missed error cases or redundant try/except.
- **Recommendation**: Standardize on Result pattern or explicit exception hierarchy. Consider using `returns` library or define custom exceptions per domain.
- **Verification**: `rg "def.*->.*Tuple.*Optional" src/` returns empty or all cases are documented.

## MG-004: Missing docstrings on public functions
- **Evidence**: `src/cdx_proxy_cli_v2/auth/rotation.py:22-189` — `RoundRobinAuthPool` class has no docstring, complex methods like `mark_result` lack parameter documentation.
- **Impact**: New developers cannot understand behavior without reading implementation, API surface unclear.
- **Recommendation**: Add Google-style or NumPy-style docstrings to all public classes and methods. Include parameter descriptions, return types, and examples.
- **Verification**: `pydocstyle src/cdx_proxy_cli_v2/` reports no missing docstrings.

## MG-005: Magic numbers without constants
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/proxy/server.py:15` — `DEFAULT_MAX_REQUEST_BODY = 10 * 1024 * 1024` (good)
  - `src/cdx_proxy_cli_v2/proxy/server.py:235` — `timeout=25` hardcoded in connection
  - `src/cdx_proxy_cli_v2/runtime/service.py:20` — `DEFAULT_STARTUP_TIMEOUT_SECONDS = 12.0` (good)
  - `src/cdx_proxy_cli_v2/auth/rotation.py:137` — `if state.rate_limit_strikes >= 5:` magic number
- **Impact**: Unclear intent, difficult to tune, scattered configuration.
- **Recommendation**: Extract all magic numbers to named constants at module level.
- **Verification**: `rg "\d{2,}" src/ --type py | grep -v "constant\|CONST\|version\|line"` finds only acceptable numeric literals.

# P2 (Medium)

## MG-006: Duplicated timestamp formatting logic
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/observability/tui.py:21-40` — `_format_ts`, `_format_age` functions
  - `src/cdx_proxy_cli_v2/observability/all_dashboard.py:26-45` — `_parse_ts`, `_fmt_ts` functions (similar but different)
- **Impact**: Inconsistent behavior, code duplication, maintenance burden.
- **Recommendation**: Consolidate timestamp utilities into `observability/time_utils.py`.
- **Verification**: `rg "def.*_.*ts\|def.*format.*time" src/` finds single module.

## MG-007: Inconsistent naming conventions
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/proxy/server.py:182` — `_extract_error_code` (underscore prefix for private)
  - `src/cdx_proxy_cli_v2/observability/tui.py:96` — `order_events_latest_first` (no underscore, but internal)
  - `src/cdx_proxy_cli_v2/auth/rotation.py` — Mix of `_mark_success` (private) vs `mark_cooldown` (public legacy)
- **Impact**: Unclear API boundaries, IDE navigation confusion.
- **Recommendation**: Establish naming convention document; run `ruff` or `pylint` with naming rules.
- **Verification**: `ruff check --select N src/` passes.

## MG-008: AuthState dataclass is mutable but used in thread-safe context
- **Evidence**: `src/cdx_proxy_cli_v2/auth/models.py:18-57` — `AuthState` is a mutable dataclass with `cooldown_until`, `blacklist_until` etc modified by `RoundRobinAuthPool`.
- **Impact**: Potential race conditions if lock not held, unclear ownership of state mutation.
- **Recommendation**: Document thread-safety requirements in docstring, consider using frozen dataclass with `replace()` pattern, or add explicit lock to AuthState.
- **Verification**: Code review confirms all mutations happen inside `self._lock` in RoundRobinAuthPool.

# P3 (Low)

## MG-009: Empty `__init__.py` files could provide module documentation
- **Evidence**: `src/cdx_proxy_cli_v2/auth/__init__.py`, `src/cdx_proxy_cli_v2/config/__init__.py`, etc. are empty (0 lines).
- **Impact**: IDE cannot show module-level documentation, unclear what the module exports.
- **Recommendation**: Add docstrings and `__all__` exports to each `__init__.py`.
- **Verification**: `wc -l src/cdx_proxy_cli_v2/*/__init__.py` shows all files have content.

## MG-010: Long parameter lists in functions
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/cli/main.py:107` — `_proxy_exports(settings, *, base_url, host, port)` 
  - `src/cdx_proxy_cli_v2/observability/collective_dashboard.py:211` — `build_collective_payload` has 11 parameters
- **Impact**: Difficult to call correctly, easy to mix up order.
- **Recommendation**: Use config objects or builder pattern for functions with >5 parameters.
- **Verification**: `ruff check --select PLR0913 src/` shows compliant code.

# Notes

- Commands run (read-only):
  - `wc -l src/cdx_proxy_cli_v2/**/*.py`
  - `rg "def.*->" src/ --type py`
  - `find src/ -name "*.py" -exec wc -l {} \;`
- Assumptions / unknowns:
  - Project may intentionally keep modules flat for simplicity
  - Some patterns may be inherited from v1 codebase
- Confidence (0-100): 85
