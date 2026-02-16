---
expert_id: "simplicity_architect"
expert_name: "Simplicity Architect"
run_id: "run_20260216_211732_cdx_proxy_cli_v2"
generated_at_utc: "2026-02-16T21:20:00Z"
read_only_target_repo: true
---

# Executive Summary

- **Top Risk 1**: Proxy server uses raw `http.server` instead of established frameworks, leading to complex manual connection handling and edge cases.
- **Top Risk 2**: Auth rotation state machine has 4 states (OK, COOLDOWN, BLACKLIST, PROBATION) with complex transition logic that's difficult to reason about.
- **Top Risk 3**: Multiple layers of configuration resolution (env vars, files, CLI args, defaults) create surprising behavior.

# P0 (Critical) — Must Fix

## SA-001: Manual HTTP proxy implementation is unnecessarily complex
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:170-320` — 150 lines of manual HTTP connection handling, streaming, error extraction, and retry logic that frameworks handle automatically.
- **Impact**: Reinventing the wheel, missing edge cases (chunked encoding, keep-alive, connection pooling), high maintenance burden.
- **Recommendation**: Evaluate `aiohttp` or `httpx` for proxy functionality. If keeping current approach, at minimum add connection pooling via `http.client` reuse.
- **Verification**: `rg "HTTPConnection\|HTTPSConnection" src/` shows usage is abstracted or `aiohttp`/`httpx` is used.

# P1 (High)

## SA-002: Configuration resolution has too many fallback levels
- **Evidence**: `src/cdx_proxy_cli_v2/config/settings.py:135-185` — `build_settings` merges file_env, os.environ, CLI args, and defaults in complex ways. Settings class has 7 fields resolved from 4 sources.
- **Impact**: Difficult to predict which value wins, debugging configuration issues is painful, surprising behavior for users.
- **Recommendation**: Simplify to clear precedence: CLI args > env vars > file > defaults. Add `--show-config` command to display effective configuration and source.
- **Verification**: `cdx2 proxy --show-config` outputs clear table of all settings with their source.

## SA-003: AuthState status state machine is implicit and complex
- **Evidence**: `src/cdx_proxy_cli_v2/auth/models.py:38-48` — `status()` method has nested conditionals determining state. `src/cdx_proxy_cli_v2/auth/rotation.py:82-135` — State transitions scattered across `_mark_success`, `_mark_blacklist`, `_mark_rate_limited`.
- **Impact**: Difficult to understand all possible state transitions, easy to introduce bugs, no visual documentation of state machine.
- **Recommendation**: Implement explicit state machine using `enum.Enum` for states and a transition table. Consider `transitions` library for complex state logic.
- **Verification**: State transitions are documented in a single place; unit tests cover all state transitions explicitly.

## SA-004: `_proxy_request` method does too much
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:236-340` — Single method handles: header building, auth selection, HTTP connection, response streaming, retry logic, error handling, tracing. 100+ lines.
- **Impact**: Cannot test individual concerns, difficult to modify one aspect without affecting others.
- **Recommendation**: Extract into focused methods:
  - `_build_upstream_request()` - Headers and body preparation
  - `_execute_upstream_request()` - HTTP call and response
  - `_handle_streaming_response()` - SSE handling
  - `_handle_retry_logic()` - Auth rotation and retry
- **Verification**: `rg "_proxy_request" src/cdx_proxy_cli_v2/proxy/server.py` shows method < 30 lines.

# P2 (Medium)

## SA-005: Collective dashboard has excessive formatting functions
- **Evidence**: `src/cdx_proxy_cli_v2/observability/collective_dashboard.py:1-331` — 14 small utility functions for formatting (human_duration, format_percent, mini_meter, etc.) that could use `humanize` library or similar.
- **Impact**: Code bloat, reinventing standard formatting, inconsistent output.
- **Recommendation**: Replace custom formatters with `humanize` or `rich` built-ins where possible.
- **Verification**: `rg "def (human_|format_|mini_)" src/` shows reduced custom formatting code.

## SA-006: TUI polling loop could use asyncio
- **Evidence**: `src/cdx_proxy_cli_v2/observability/tui.py:232-270` — `run_trace_tui` uses `while True` with `time.sleep()` for polling. Could be cleaner with async.
- **Impact**: Blocking sleep wastes cycles, harder to add multiple data sources.
- **Recommendation**: If adding more data sources, consider async architecture. For current single-source use, document why polling is acceptable.
- **Verification**: Code is documented or converted to async.

## SA-007: Multiple ways to start the proxy (run-server vs start_service)
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/runtime/service.py:121-165` — `start_service` spawns subprocess
  - `src/cdx_proxy_cli_v2/proxy/server.py:470-488` — `run_proxy_server` runs in-process
  - `src/cdx_proxy_cli_v2/cli/main.py:66-70` — `handle_run_server` is hidden command
- **Impact**: Confusing for contributors, two code paths to maintain.
- **Recommendation**: Document the architecture decision: subprocess isolation vs in-process. Add comment explaining the design.
- **Verification**: Architecture is documented in README or code comments.

# P3 (Low)

## SA-008: Box drawing characters defined inline
- **Evidence**: `src/cdx_proxy_cli_v2/observability/collective_dashboard.py:17-40` — Custom box definitions for `OPEN_RIGHT_ROUNDED` and `OPEN_RIGHT_DOUBLE`.
- **Impact**: Visual customization, but could use `rich.box` standard styles.
- **Recommendation**: Evaluate if `rich.box.ROUNDED` or similar meets needs before custom definitions.
- **Verification**: Custom boxes are justified or replaced with standard styles.

## SA-009: Emergency shutdown handling could be cleaner
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:447-465` — Signal handler pattern with `stop_requested` flag and `server.initiate_shutdown()` threading.
- **Impact**: Standard pattern, but could use context managers.
- **Recommendation**: Consider `contextlib` pattern or signal-based context manager for cleaner shutdown handling.
- **Verification**: Code is idiomatic or documented.

# Notes

- Commands run (read-only):
  - `rg "def " src/cdx_proxy_cli_v2/proxy/server.py | wc -l`
  - `rg "while True" src/ --type py`
  - `rg "import http" src/ --type py`
- Assumptions / unknowns:
  - Project may intentionally avoid async for simplicity
  - Subprocess isolation may be intentional for reliability
- Confidence (0-100): 80
