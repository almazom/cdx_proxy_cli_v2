# Testability Scout Report

- Logic-level coverage is already strong.
- Remaining gaps are deterministic tests around service lifecycle branches and long-running loops.

## Findings

1. **P1 — `start_service` stale-port and retry branches need deterministic coverage**
   - Reference: `src/cdx_proxy_cli_v2/runtime/service.py:339`

2. **P1 — `run_proxy_server` couples signal wiring and real server loop**
   - Reference: `src/cdx_proxy_cli_v2/proxy/server.py:513`

3. **P2 — trace TUI loop lacks a deterministic stop seam**
   - Reference: `src/cdx_proxy_cli_v2/observability/tui.py:220`

## Top Recommendation

The lifecycle hardening card includes new regression tests for the most failure-prone branches.
