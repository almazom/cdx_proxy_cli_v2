# cdx_proxy_cli_v2 Architecture

## Goals

- Keep proxy behavior stable while reducing structural complexity.
- Make traceability first-class for debugging auth rotation behavior.
- Keep the runtime local-only and easy to operate from terminal.

## Layered Structure

- `src/cdx_proxy_cli_v2/cli/main.py`
  - command surface (`proxy`, `status`, `stop`, `trace`, `logs`)
- `src/cdx_proxy_cli_v2/runtime/service.py`
  - background lifecycle and pid/state/log files
- `src/cdx_proxy_cli_v2/proxy/server.py`
  - transport loop, management endpoints, attempt logging
- `src/cdx_proxy_cli_v2/auth/rotation.py`
  - round-robin and cooldown domain policy
- `src/cdx_proxy_cli_v2/auth/store.py`
  - auth file loading and normalization
- `src/cdx_proxy_cli_v2/observability/trace_store.py`
  - bounded in-memory trace events
- `src/cdx_proxy_cli_v2/observability/event_log.py`
  - durable JSONL audit stream
- `src/cdx_proxy_cli_v2/observability/all_dashboard.py`
  - `cdx2 all` summary and per-key dashboard
- `src/cdx_proxy_cli_v2/observability/tui.py`
  - live trace rendering

## Request Flow

1. Incoming request arrives at proxy.
2. `auth.rotation.RoundRobinAuthPool` selects an available auth.
3. Request path and headers are normalized by `proxy/rules.py`.
4. Upstream call executes.
5. Attempt result is written to:
   - in-memory `TraceStore`
   - JSONL `rr_proxy_v2.events.jsonl`
6. If status is `401` or `429`, auth enters cooldown and next auth is tried.
7. Final response is returned to caller.

## Traceability Design

Each attempt gets these key fields:

- `request_id`: stable across retries of the same inbound request
- `attempt`: retry number
- `auth_file` / `auth_email`: which credential served the attempt
- `status` and `latency_ms`
- `path`, `route`, `method`

This gives a clear causal chain for "what happened and why" during rotation.
