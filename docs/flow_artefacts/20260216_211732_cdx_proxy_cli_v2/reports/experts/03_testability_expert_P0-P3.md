---
expert_id: "testability_expert"
expert_name: "Testability Expert"
run_id: "run_20260216_211732_cdx_proxy_cli_v2"
generated_at_utc: "2026-02-16T21:20:00Z"
read_only_target_repo: true
---

# Executive Summary

- **Top Risk 1**: No tests for `proxy/server.py` (488 lines) - the most critical and complex module is untested.
- **Top Risk 2**: No tests for `config/settings.py` which has complex environment/file/CLI merging logic.
- **Top Risk 3**: Tests rely heavily on `monkeypatch` for time mocking, making them brittle and hard to run in isolation.

# P0 (Critical) — Must Fix

## TE-001: Zero test coverage for proxy server module
- **Evidence**: `tests/` directory has no `test_server.py` or `tests/proxy/test_server.py`. The most complex module with 488 lines has zero unit tests.
- **Impact**: Cannot safely refactor, bugs in proxy logic go undetected, streaming and retry logic untested.
- **Recommendation**: Create `tests/proxy/test_server.py` with tests for:
  - ProxyHandler routing (management vs proxy)
  - Auth header injection
  - Response streaming
  - Retry logic on 401/403/429
  - Error response handling
- **Verification**: `pytest tests/proxy/test_server.py -v` runs 20+ tests with >80% coverage of server.py.

## TE-002: Config settings merging logic untested
- **Evidence**: `tests/` has no `test_settings.py`. `build_settings` function has complex precedence logic across env vars, files, and CLI args.
- **Impact**: Configuration bugs could cause production issues, cannot verify precedence rules.
- **Recommendation**: Create `tests/config/test_settings.py` with tests for:
  - Precedence: CLI > env > file > default
  - Path expansion (~, relative)
  - Port validation
  - Management key generation
- **Verification**: `pytest tests/config/test_settings.py -v` runs 15+ tests.

# P1 (High)

## TE-003: Runtime service lifecycle untested
- **Evidence**: `tests/` has no `test_service.py`. `runtime/service.py` has 357 lines with PID management, process spawning, and graceful shutdown - all untested.
- **Impact**: Cannot verify service starts correctly, handles stale PIDs, or shuts down cleanly.
- **Recommendation**: Create `tests/runtime/test_service.py` using subprocess mocking:
  - Test `start_service` when already running
  - Test `stop_service` with/without running process
  - Test stale PID file handling
  - Test startup timeout
- **Verification**: `pytest tests/runtime/test_service.py -v` runs 10+ tests.

## TE-004: HTTP client has no error path tests
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/http_client.py:1-30` - `fetch_json` has no tests. Error handling for timeouts, HTTP errors, and JSON parsing is untested.
- **Impact**: Network errors could crash the application, timeout behavior unknown.
- **Recommendation**: Create `tests/proxy/test_http_client.py` with:
  - Mock `urlopen` for success cases
  - Test timeout exceptions
  - Test HTTP error responses
  - Test invalid JSON responses
- **Verification**: `pytest tests/proxy/test_http_client.py -v` passes.

## TE-005: Time-dependent tests use monkeypatch which is pytest-specific
- **Evidence**: `tests/auth/test_rotation.py:22-71` — Uses `monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", ...)` pattern extensively.
- **Impact**: Tests cannot run outside pytest, tight coupling to test framework, harder to understand.
- **Recommendation**: Inject time provider as dependency. Add `time_provider: Callable[[], float] = time.time` parameter to `RoundRobinAuthPool.__init__` and `pick()`.
- **Verification**: Tests use injected time provider, not monkeypatch.

# P2 (Medium)

## TE-006: No integration tests for CLI commands
- **Evidence**: No `tests/cli/` directory. `handle_proxy`, `handle_status`, `handle_doctor`, etc. are untested.
- **Impact**: CLI argument parsing bugs, output format changes undetected.
- **Recommendation**: Create `tests/cli/test_main.py` with:
  - `test_proxy_command_starts_service()`
  - `test_status_command_shows_table()`
  - `test_doctor_command_json_output()`
  - Use `subprocess.run(["cdx2", ...])` or mock service functions
- **Verification**: `pytest tests/cli/ -v` runs 10+ tests.

## TE-007: Test fixtures not defined in conftest.py
- **Evidence**: `tests/conftest.py:1-9` — Only path setup, no shared fixtures for auth records, mock servers, or sample events.
- **Impact**: Test code duplication, inconsistent test data.
- **Recommendation**: Add fixtures to conftest.py:
  - `sample_auth_record()` - AuthRecord factory
  - `mock_proxy_server()` - Fixture for integration tests
  - `sample_trace_events()` - Sample event data
- **Verification**: `rg "@pytest.fixture" tests/conftest.py` finds 5+ fixtures.

## TE-008: Observability TUI untestable due to infinite loop
- **Evidence**: `src/cdx_proxy_cli_v2/observability/tui.py:232-270` — `run_trace_tui` has `while True` loop with no escape hatch for testing.
- **Impact**: Cannot unit test TUI rendering logic.
- **Recommendation**: Add `max_iterations: Optional[int] = None` parameter. If set, loop exits after N iterations. This allows testing without infinite loops.
- **Verification**: `pytest tests/observability/test_tui.py` can test TUI logic.

# P3 (Low)

## TE-009: Missing test coverage metrics in CI
- **Evidence**: No `pytest-cov` configuration in `pyproject.toml` or CI workflow.
- **Impact**: Coverage regressions go unnoticed.
- **Recommendation**: Add coverage configuration:
  ```toml
  [tool.pytest.ini_options]
  addopts = "--cov=src/cdx_proxy_cli_v2 --cov-report=term-missing --cov-fail-under=70"
  ```
- **Verification**: CI fails if coverage drops below threshold.

## TE-010: Event log file tests missing
- **Evidence**: `src/cdx_proxy_cli_v2/observability/event_log.py` has no direct tests.
- **Impact**: JSON formatting bugs, file handling errors undetected.
- **Recommendation**: Create `tests/observability/test_event_log.py` with tests for write, append, and tail functionality.
- **Verification**: `pytest tests/observability/test_event_log.py` passes.

# Notes

- Commands run (read-only):
  - `find tests/ -name "*.py" -exec basename {} \;`
  - `pytest --collect-only 2>/dev/null | grep "test session starts"`
  - `rg "monkeypatch" tests/ --type py`
- Assumptions / unknowns:
  - TaaD tests in `tests/taad/` may cover some scenarios but appear to be contract tests
  - Project may have integration tests elsewhere
- Confidence (0-100): 90
