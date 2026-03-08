# CARD-004: Document configuration precedence

## Metadata

| Field | Value |
|-------|-------|
| ID | CARD-004 |
| Priority | P0 |
| Complexity | 1 hour |
| Status | draft |
| Blocked by | — |

## Context

**Source Finding**: P0-004 (Simplicity Report)

**Problem**: Configuration can come from CLI args, env vars, or .env files. Precedence rules are complex and not clearly documented.

**File**: `README.md`, `src/cdx_proxy_cli_v2/config/settings.py:114-135`

## Goal

Add clear documentation explaining the configuration precedence hierarchy.

## Acceptance Criteria

- [ ] Add "Configuration" section to README.md
- [ ] Document precedence order: CLI args > env vars > .env file > defaults
- [ ] Provide examples for each configuration method
- [ ] Document all configurable options in a table
- [ ] Add example .env file

## Implementation Notes

```markdown
## Configuration

Configuration can be provided via:

1. **CLI arguments** (highest priority)
2. **Environment variables** 
3. **`.env` file** in auth directory
4. **Defaults** (lowest priority)

### Precedence Example

```bash
# Default port: 0 (auto-assign)
# .env file: CLIPROXY_PORT=8181
# Environment: export CLIPROXY_PORT=8282
# CLI: --port 8383

# Result: port 8383 (CLI wins)
```

### Available Options

| Option | CLI Flag | Env Variable | Default |
|--------|----------|--------------|---------|
| Auth directory | `--auth-dir` | `CLIPROXY_AUTH_DIR` | `~/.codex/_auths` |
| Host | `--host` | `CLIPROXY_HOST` | `127.0.0.1` |
| Port | `--port` | `CLIPROXY_PORT` | `0` (auto) |
| Upstream | `--upstream` | `CLIPROXY_UPSTREAM` | `https://chatgpt.com/backend-api` |
| Management key | `--management-key` | `CLIPROXY_MANAGEMENT_KEY` | (generated) |
| Trace max | `--trace-max` | `CLIPROXY_TRACE_MAX` | `500` |
```

## Definition of Done

- [ ] Configuration section added to README
- [ ] All options documented
- [ ] Examples provided
- [ ] Reviewed for clarity
