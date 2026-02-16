# cdx_proxy_cli_v2

`cdx_proxy_cli_v2` is a clean-split rewrite of `cdx_proxy_cli` focused on:

- smaller modules with single responsibility
- explicit request traceability (`request_id`, attempts, auth selection)
- simple service lifecycle (`proxy`, `status`, `stop`, `trace`)
- localhost-first defaults with management-key protection

## Why this V2 layout

The current project works, but much behavior is concentrated in large files.
This V2 keeps behavior similar while splitting complexity into narrow modules:

- `src/cdx_proxy_cli_v2/config/settings.py`: runtime/env config and persistence
- `src/cdx_proxy_cli_v2/auth/store.py`: auth discovery and token extraction
- `src/cdx_proxy_cli_v2/auth/rotation.py`: round-robin and cooldown policy
- `src/cdx_proxy_cli_v2/observability/trace_store.py`: in-memory trace ring buffer
- `src/cdx_proxy_cli_v2/observability/event_log.py`: JSONL event sink
- `src/cdx_proxy_cli_v2/proxy/rules.py`: request routing/header rewriting rules
- `src/cdx_proxy_cli_v2/proxy/server.py`: HTTP proxy transport and management endpoints
- `src/cdx_proxy_cli_v2/runtime/service.py`: background process lifecycle
- `src/cdx_proxy_cli_v2/observability/tui.py`: Rich live trace monitor
- `src/cdx_proxy_cli_v2/cli/main.py`: command orchestration

## Quick Start

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
pip install -e .
cdx2 proxy
```

Export proxy env in your current shell:

```bash
eval "$(cdx2 proxy --print-env-only)"
```

Open trace TUI:

```bash
cdx2 trace
```

Stop proxy:

```bash
cdx2 stop
```

## Commands

- `cdx2 proxy`: start/reuse service
- `cdx2 proxy --print-env`: print shell exports for current terminal (includes status line on stderr)
- `cdx2 proxy --print-env-only`: print only `export ...` lines (safe for `eval`)
- `cdx2 status`: show running status and runtime details
- `cdx2 doctor`: show key rotation state (`whitelist/probation/cooldown/blacklist`)
- `cdx2 trace`: open live trace TUI
- `cdx2 all`: show all key cards dashboard (same style as v1)
- `cdx2 all --json`: machine-readable variant for AI agents/automation
- `cdx2 stop`: shutdown proxy
- `cdx2 logs --lines 120`: tail proxy log file

## Runtime Files

Under `~/.codex/_auths` (or `CLIPROXY_AUTH_DIR`):

- `rr_proxy_v2.pid`
- `rr_proxy_v2.state.json`
- `rr_proxy_v2.log`
- `rr_proxy_v2.events.jsonl`
- `.env`

## Management Endpoints

- `GET /debug`
- `GET /trace?limit=200`
- `GET /health?refresh=1`
- `GET /auth-files`
- `POST /shutdown`

All management endpoints require `X-Management-Key`.

## Security Defaults

- default bind: `127.0.0.1`
- non-loopback bind blocked unless `--allow-non-loopback`
- auth tokens are never written to trace/event payloads

## Rotation Strategy (Blacklist/Whitelist)

- `401/403`: key is temporarily blacklisted (outlier ejection)
- `429`: key gets exponential cooldown and is skipped by round-robin
- re-entry: blacklisted key must pass probation before full whitelist return
- token refresh: if auth file token changes, penalties reset for that key

## Tests

```bash
python3 -m pytest
```

## Quality Gate (TaaD)

- Report template: `docs/quality/TAAD_REPORT_TEMPLATE.md`
- Quick checklist: `docs/quality/TAAD_CHECKLIST.md`
- Test matrix: `docs/quality/TAAD_TEST_MATRIX.md`
- Executable contracts: `tests/taad/README.md`
- Required CI status setup: `docs/quality/CI_REQUIRED_STATUS.md`
