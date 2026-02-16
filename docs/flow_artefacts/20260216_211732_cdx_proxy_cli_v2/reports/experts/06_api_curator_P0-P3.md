---
expert_id: "api_curator"
expert_name: "API Curator"
run_id: "run_20260216_211732_cdx_proxy_cli_v2"
generated_at_utc: "2026-02-16T21:20:00Z"
read_only_target_repo: true
---

# Executive Summary

- **Top Risk 1**: CLI error messages are inconsistent - some go to stdout, some to stderr, some return exit codes, some raise exceptions.
- **Top Risk 2**: JSON output format varies between commands (`doctor --json` vs `all --json` have different structures).
- **Top Risk 3**: No API versioning strategy for management endpoints or CLI output.

# P0 (Critical) — Must Fix

## AC-001: Inconsistent error output destination (stdout vs stderr)
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/cli/main.py:102-103` — `print(f"Proxy started...")` goes to stdout
  - `src/cdx_proxy_cli_v2/cli/main.py:90` — `print("Proxy not running...", file=sys.stderr)` goes to stderr
  - `src/cdx_proxy_cli_v2/cli/main.py:430` — `print(str(exc), file=sys.stderr)` for RuntimeError
- **Impact**: Scripts parsing output cannot reliably separate data from errors, breaks Unix convention.
- **Recommendation**: Standardize error handling:
  - All error/diagnostic messages → stderr
  - All data output → stdout
  - Add `--quiet` flag to suppress non-error output
- **Verification**: `cdx2 invalid-command 2>/dev/null` produces no output; `cdx2 status 2>/dev/null` produces table.

# P1 (High)

## AC-002: JSON output format inconsistent between commands
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/cli/main.py:155-170` — `handle_doctor` returns nested structure with `ok`, `policy`, `summary`, `accounts`
  - `src/cdx_proxy_cli_v2/cli/main.py:205-220` — `handle_all` returns `ok`, `aggregate`, `availability`, `accounts`, `thresholds`
  - Different field naming: `summary` vs `aggregate`, different nesting levels
- **Impact**: Automation tools must handle multiple formats, higher integration cost.
- **Recommendation**: Standardize JSON schema:
  ```json
  {
    "ok": true,
    "command": "doctor|all|status",
    "timestamp": "ISO8601",
    "data": { ... command-specific ... },
    "errors": []
  }
  ```
- **Verification**: JSON schema validator passes on all `--json` outputs.

## AC-003: Exit codes not documented or consistent
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/cli/main.py:107` — Returns 0 for success
  - `src/cdx_proxy_cli_v2/cli/main.py:91` — Returns 1 for proxy not healthy
  - `src/cdx_proxy_cli_v2/cli/main.py:432` — Returns 1 for RuntimeError
  - `src/cdx_proxy_cli_v2/cli/main.py:434` — Returns 2 for ValueError
- **Impact**: Scripts cannot reliably interpret exit codes.
- **Recommendation**: Document exit codes in CLI help:
  - 0: Success
  - 1: Runtime error (service not running, etc.)
  - 2: User error (invalid arguments)
  - 3: Configuration error
  - Document in `cdx2 --help` and README
- **Verification**: `cdx2 --help` includes exit code documentation.

## AC-004: No structured logging format option
- **Evidence**: `src/cdx_proxy_cli_v2/observability/event_log.py` writes JSONL, but `print()` statements throughout code output unstructured text.
- **Impact**: Cannot integrate with log aggregation systems, hard to parse logs programmatically.
- **Recommendation**: Add `--log-format=json` option to proxy command, route all logs through structured logger.
- **Verification**: `cdx2 proxy --log-format=json` produces only JSONL output.

# P2 (Medium)

## AC-005: Management endpoint paths are inconsistent
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/rules.py:38-46` — `/debug`, `/trace`, `/health`, `/auth-files`, `/shutdown` - no common prefix, mixed naming (hyphen vs no hyphen).
- **Impact**: Hard to document, potential conflicts with proxied paths.
- **Recommendation**: Use consistent prefix like `/_proxy/`:
  - `/_proxy/debug`
  - `/_proxy/trace`
  - `/_proxy/health`
  - `/_proxy/auth-files`
  - `/_proxy/shutdown`
- **Verification**: All management routes start with `/_proxy/`.

## AC-006: CLI argument naming inconsistent
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/cli/main.py:43` — `--auth-dir` (hyphen)
  - `src/cdx_proxy_cli_v2/cli/main.py:177` — `--warn-at` (hyphen)
  - `src/cdx_proxy_cli_v2/cli/main.py:56` — `--allow-non-loopback` (hyphen)
  - But environment variables use underscores: `CLIPROXY_AUTH_DIR`
- **Impact**: Slight UX friction, requires memorization.
- **Recommendation**: This is consistent with POSIX conventions (CLI uses hyphens, env uses underscores). Document the mapping clearly in help text.
- **Verification**: `cdx2 proxy --help` shows env var mapping.

## AC-007: Health endpoint returns different structure than doctor command
- **Evidence**: 
  - `src/cdx_proxy_cli_v2/proxy/server.py:219-223` — `/health` returns `{"ok": bool, "accounts": [...]}`
  - `src/cdx_proxy_cli_v2/cli/main.py:155-170` — `doctor` returns more fields including `policy`, `summary`
- **Impact**: Confusing API surface, unclear which to use.
- **Recommendation**: Document intended use cases:
  - `/health` - Lightweight health check for monitoring
  - `doctor` - Detailed diagnostics for troubleshooting
- **Verification**: README documents when to use each.

# P3 (Low)

## AC-008: No API version in responses
- **Evidence**: All JSON responses lack version field.
- **Impact**: Cannot evolve API safely, breaking changes affect all clients.
- **Recommendation**: Add `api_version: "1.0"` to all JSON responses. Document versioning policy.
- **Verification**: All JSON outputs include `api_version` field.

## AC-009: No pagination for trace endpoint
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:225-234` — `/trace?limit=N` returns last N events, but no cursor-based pagination.
- **Impact**: Cannot efficiently retrieve large trace histories.
- **Recommendation**: Add cursor-based pagination:
  - `/trace?limit=100&cursor=abc123`
  - Response includes `next_cursor` field
- **Verification**: Pagination works with >1000 events.

## AC-010: CLI help text could be more discoverable
- **Evidence**: `src/cdx_proxy_cli_v2/cli/main.py:243-272` — `proxy` command has detailed epilog, but other commands lack examples.
- **Impact**: Users may not discover advanced features.
- **Recommendation**: Add examples to all command help texts:
  - `status` - Show example output
  - `doctor` - Explain what each field means
  - `trace` - Show keyboard shortcuts (if any)
- **Verification**: All commands have `Examples:` section in help.

# Notes

- Commands run (read-only):
  - `cdx2 --help` (simulated via code reading)
  - `rg "print\(" src/cdx_proxy_cli_v2/cli/main.py`
  - `rg "file=sys.stderr\|file=sys.stdout" src/ --type py`
- Assumptions / unknowns:
  - Project may target single-user CLI use, not programmatic integration
  - API versioning may not be needed for current scope
- Confidence (0-100): 85
