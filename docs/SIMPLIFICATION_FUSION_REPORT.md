# Simplification Fusion Report

Date: 2026-03-05  
Scope: recently modified files in `cdx_proxy_cli_v2`
Method: 6 subagents run with the same `code-simplifier` mindset (preserve behavior, improve clarity, no edits during analysis)

## Candidate 1 — Proxy request retry loop extraction
- **Title:** Isolate the per-auth upstream attempt from the retry loop in `_proxy_request`
- **File:** `src/cdx_proxy_cli_v2/proxy/server.py`
- **Lines:** `342-421`
- **Problem:** One loop currently mixes auth selection, upstream HTTP calls, exception mapping, streaming handling, trace/log side effects, and retry policy.
- **Plan:**
  1. Extract try/except request/response block into a helper returning an attempt result object.
  2. Keep connection/stream ownership inside that helper.
  3. Reduce outer loop to: pick auth → inject headers → record/mark → retry decision.
  4. Keep final response writing path unchanged.
- **Safety:** Structural refactor only; preserve status/error mapping, size limits, SSE behavior, and auth rotation triggers.
- **Validate:** normal JSON success, SSE streaming, oversized response (413), upstream failure (502), 401/403/429 retry rotation behavior.

## Candidate 2 — Shared preflight guard for doctor/reset
- **Title:** Extract shared “healthy proxy + base_url” guard for doctor/reset
- **File:** `src/cdx_proxy_cli_v2/cli/main.py`
- **Lines:** `179-186, 355-362`
- **Problem:** `handle_doctor()` and `handle_reset()` duplicate identical service preflight logic and failure path.
- **Plan:**
  1. Add small helper to resolve base URL from status/settings and enforce healthy check.
  2. Move repeated stderr+failure signaling there.
  3. Replace both duplicated blocks with helper call.
  4. Leave all downstream command logic unchanged.
- **Safety:** Same control flow, same message text, same base URL precedence, same exit codes.
- **Validate:** doctor/reset when proxy down vs up; compare output and exit code parity.

## Candidate 3 — Numeric settings resolution dedup
- **Title:** Collapse duplicated numeric-setting resolution in `build_settings`
- **File:** `src/cdx_proxy_cli_v2/config/settings.py`
- **Lines:** `179-210`
- **Problem:** Four repeated override/env/default branches (`port`, `trace_max`, `request_timeout`, `compact_timeout`) obscure a shared pattern.
- **Plan:**
  1. Add local resolver for “CLI override else env parse with default”.
  2. Parameterize parser/bounds (`parse_port` for port, `parse_positive_int` for others).
  3. Replace repetitive blocks with resolver calls.
  4. Keep precedence `CLI > env > constant` unchanged.
- **Safety:** Pure extraction if existing parsers and defaults are reused unchanged.
- **Validate:** matrix for each numeric field (unset/invalid/negative/zero/bounds/valid/CLI override).

## Candidate 4 — Management route lookup table
- **Title:** Replace repetitive management route conditionals with table lookup
- **File:** `src/cdx_proxy_cli_v2/proxy/rules.py`
- **Lines:** `48-62`
- **Problem:** `management_route()` uses repeated static `if path == ...` checks.
- **Plan:**
  1. Add `MANAGEMENT_ROUTES` dict.
  2. Keep `path_only = urlsplit(...).path` logic.
  3. Replace `if` chain with `MANAGEMENT_ROUTES.get(path_only)`.
  4. Preserve `Optional[str]` behavior (`None` for unknown paths).
- **Safety:** Direct literal mapping replacement.
- **Validate:** all known routes, unknown route, and querystring path behavior.

## Candidate 5 — stop/status endpoint resolution dedup
- **Title:** Deduplicate state-based endpoint resolution in stop/status paths
- **File:** `src/cdx_proxy_cli_v2/runtime/service.py`
- **Lines:** `448-455, 490-497`
- **Problem:** `stop_service()` and `service_status()` duplicate host/port/base_url parsing/fallback from state.
- **Plan:**
  1. Add helper like `_resolve_endpoint_from_state(settings, state)`.
  2. Use helper in `stop_service()`.
  3. Use helper in `service_status()`.
  4. Keep conversion/fallback behavior exactly identical.
- **Safety:** Mechanical extraction only.
- **Validate:** state with valid port, invalid port, and missing port; compare host/port/base_url outputs.

## Candidate 6 — Remove unused timestamp path in TUI rows
- **Title:** Remove unused timestamp formatting from event row assembly
- **File:** `src/cdx_proxy_cli_v2/observability/tui.py`
- **Lines:** `3, 17-23, 88-98, 198`
- **Problem:** `_event_line()` computes/returns `ts` (via `_format_ts()`), but `_build_view()` never uses it.
- **Plan:**
  1. Remove `ts` from `_event_line()` return.
  2. Update unpacking in `_build_view()`.
  3. Delete unused `_format_ts()` and `datetime` import.
  4. Run lint/tests and TUI smoke check.
- **Safety:** Removes dead intermediate data only.
- **Validate:** search for `_format_ts` references, run tests, smoke-run trace TUI (preview on/off).

---

## Fusion Ranking (impact-first)
1. **Candidate 1 (`proxy/server.py`)** — highest clarity gain in most complex hot path.
2. **Candidate 3 (`config/settings.py`)** — strong maintainability gain, low risk.
3. **Candidate 2 (`cli/main.py`)** — medium gain, low risk, immediate readability improvement.
4. **Candidate 5 (`runtime/service.py`)** — medium gain, low risk.
5. **Candidate 6 (`observability/tui.py`)** — small-to-medium gain, very low risk.
6. **Candidate 4 (`proxy/rules.py`)** — small gain, very low risk.

## Recommended first simplification to execute
**Candidate 1: `_proxy_request` per-attempt extraction in `proxy/server.py`**

Why first:
- Largest concentration of mixed concerns in current modified code.
- Most improvement in readability/testability without changing behavior.
- Reduces future bug risk in retry + streaming + auth-rotation interactions.

Execution plan (implementation phase):
1. Introduce an internal attempt-result structure (status/headers/body/error/error_code/stream handles).
2. Extract one helper for a single upstream attempt (request + response parsing + error mapping).
3. Keep retry loop as orchestration only (pick auth, call helper, record attempt, mark result, retry condition).
4. Keep final response write path and management behavior untouched.
5. Run targeted proxy tests + full suite.

_No code changes were made in this report step; this is analysis + fused recommendation only._
