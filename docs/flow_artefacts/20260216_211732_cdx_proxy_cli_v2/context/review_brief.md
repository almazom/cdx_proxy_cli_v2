# Context Brief: cdx_proxy_cli_v2

> Run ID: run_20260216_211732_cdx_proxy_cli_v2  
> Generated: 2026-02-16T21:17:32Z

## Project Overview

**Name:** cdx-proxy-cli-v2  
**Version:** 0.1.0  
**Python:** >=3.9  
**License:** MIT

**Description:** A simplified localhost proxy CLI with request traceability and TUI (Terminal User Interface). This is a clean-split rewrite focused on smaller modules with single responsibility, explicit request traceability, and simple service lifecycle.

## Project Stats

| Metric | Value |
|--------|-------|
| Source Files | 20 Python files |
| Source LOC | ~3,029 lines |
| Test Files | 10 test files |
| Test LOC | ~686 lines |
| Total Files | 45 (including tests) |

## Architecture

### Module Structure

```
src/cdx_proxy_cli_v2/
├── __init__.py           (3 lines)
├── __main__.py           (5 lines)
├── cli/
│   ├── __init__.py       (3 lines)
│   └── main.py           (424 lines) - Command orchestration, argparse handlers
├── config/
│   ├── __init__.py       (0 lines)
│   └── settings.py       (220 lines) - Runtime/env config, persistence, Settings dataclass
├── auth/
│   ├── __init__.py       (0 lines)
│   ├── models.py         (68 lines) - AuthRecord, AuthState dataclasses
│   ├── store.py          (88 lines) - Auth discovery, token extraction
│   └── rotation.py       (189 lines) - Round-robin pool with cooldown/blacklist/probation
├── proxy/
│   ├── __init__.py       (0 lines)
│   ├── http_client.py    (30 lines) - Simple HTTP client wrapper
│   ├── rules.py          (106 lines) - Request routing, header rewriting
│   └── server.py         (488 lines) - HTTP proxy transport, management endpoints
├── runtime/
│   ├── __init__.py       (0 lines)
│   └── service.py        (357 lines) - Background process lifecycle management
├── observability/
│   ├── __init__.py       (0 lines)
│   ├── trace_store.py    (34 lines) - In-memory trace ring buffer
│   ├── event_log.py      (58 lines) - JSONL event sink
│   ├── tui.py            (277 lines) - Rich live trace monitor
│   ├── all_dashboard.py  (248 lines) - Key cards dashboard
│   └── collective_dashboard.py (331 lines) - Collective usage dashboard
├── health_snapshot.py    (146 lines) - Health snapshot utilities
└── limits_domain.py      (86 lines) - JWT decoding, usage domain logic
```

### Key Components

1. **CLI Layer** (`cli/main.py`): Argparse-based command interface with handlers for:
   - `proxy`: Start/reuse proxy service
   - `status`: Show service status
   - `doctor`: Rotation state diagnostics
   - `stop`: Shutdown proxy
   - `trace`: Live trace TUI
   - `logs`: Tail service logs
   - `all`: Keys dashboard
   - `run-server`: Internal server command

2. **Proxy Server** (`proxy/server.py`): ThreadingHTTPServer with:
   - Management endpoints: `/debug`, `/trace`, `/health`, `/auth-files`, `/shutdown`
   - Request proxying with auth rotation
   - Stream response handling (SSE)
   - Error code extraction and retry logic

3. **Auth Rotation** (`auth/rotation.py`): Thread-safe pool with:
   - Round-robin selection
   - Cooldown for rate limits (429)
   - Blacklist for auth failures (401/403)
   - Probation-based re-entry

4. **Service Lifecycle** (`runtime/service.py`): Background process management with:
   - PID file management
   - State persistence
   - Startup timeout handling
   - Graceful shutdown

5. **Observability**:
   - `trace_store.py`: In-memory ring buffer
   - `event_log.py`: JSONL file logging
   - `tui.py`: Rich-based live dashboard

## Commands

| Command | Description |
|---------|-------------|
| `cdx2 proxy` | Start/reuse service |
| `cdx2 proxy --print-env` | Print shell exports with status |
| `cdx2 proxy --print-env-only` | Print only exports (for eval) |
| `cdx2 status` | Service status |
| `cdx2 doctor` | Rotation diagnostics |
| `cdx2 trace` | Live trace TUI |
| `cdx2 all` | Keys dashboard |
| `cdx2 stop` | Shutdown proxy |
| `cdx2 logs` | Tail logs |

## Runtime Files

Under `~/.codex/_auths` (or `CLIPROXY_AUTH_DIR`):
- `rr_proxy_v2.pid` - Process ID
- `rr_proxy_v2.state.json` - Runtime state
- `rr_proxy_v2.log` - Log file
- `rr_proxy_v2.events.jsonl` - Event log
- `.env` - Environment file

## Security Features

- Default bind: 127.0.0.1 (loopback only)
- Non-loopback bind blocked unless `--allow-non-loopback`
- Management key required for management endpoints
- Auth tokens never written to trace/event payloads

## Dependencies

- **rich** >=13.7,<15 (for TUI/dashboard rendering)

## Test Coverage

Tests are organized under `tests/`:
- `tests/auth/test_rotation.py` - Rotation logic tests
- `tests/proxy/test_rules.py` - Routing rules tests
- `tests/observability/` - TUI, trace store, dashboard tests
- `tests/taad/` - Contract-based tests (traceability, auth, management, rotation policy)

## Key Observations

1. **Clean architecture**: Well-separated concerns with focused modules
2. **Thread-safety**: Uses `threading.Lock()` for auth pool
3. **Error handling**: Comprehensive try/except with error logging
4. **Configuration**: Multiple sources (env vars, files, CLI args) with merge logic
5. **No external framework**: Uses Python stdlib `http.server` for proxy

## Potential Areas for Review

1. **Security**: Token handling, management key security, injection risks
2. **Performance**: HTTP connection pooling, memory management in trace store
3. **Testability**: Test coverage gaps, mocking strategies
4. **Maintainability**: Code duplication, naming consistency
5. **API Design**: CLI ergonomics, error messages
6. **Simplicity**: Complex flows that could be simplified
