# Card 0001: Split main.py into cli/commands/ modules

| Field | Value |
|-------|-------|
| Phase | Phase 1: Implementation |
| Story Points | 2 |
| Estimated Hours | 2 |
| Depends On | None |

## Intent

Break the 1057-line `cli/main.py` God file into focused modules under `cli/commands/`. Keep `main.py` as a thin router: `build_parser()` + `main()` + shared helpers only.

## Files

- `src/cdx_proxy_cli_v2/cli/main.py` (trim to parser + router)
- `src/cdx_proxy_cli_v2/cli/commands/__init__.py` (new)
- `src/cdx_proxy_cli_v2/cli/commands/proxy.py` (new — `handle_proxy`)
- `src/cdx_proxy_cli_v2/cli/commands/status.py` (new — `handle_status`)
- `src/cdx_proxy_cli_v2/cli/commands/doctor.py` (new — `handle_doctor`)
- `src/cdx_proxy_cli_v2/cli/commands/stop.py` (new — `handle_stop`)
- `src/cdx_proxy_cli_v2/cli/commands/trace.py` (new — `handle_trace`)
- `src/cdx_proxy_cli_v2/cli/commands/logs.py` (new — `handle_logs`)
- `src/cdx_proxy_cli_v2/cli/commands/limits.py` (new — `handle_limits`)
- `src/cdx_proxy_cli_v2/cli/commands/reset.py` (new — `handle_reset`)
- `src/cdx_proxy_cli_v2/cli/commands/rotate.py` (new — `handle_rotate`)
- `src/cdx_proxy_cli_v2/cli/commands/all.py` (new — `handle_all`)
- `src/cdx_proxy_cli_v2/cli/commands/migrate.py` (new — `handle_migrate`)
- `src/cdx_proxy_cli_v2/cli/commands/run_server.py` (new — `handle_run_server`)

## Implementation Tasks

- [ ] Create `cli/commands/__init__.py` — import all `handle_*` functions for easy re-export
- [ ] Move each `handle_*` function from `main.py` into its own file under `cli/commands/`
- [ ] Keep shared helpers (`_add_runtime_options`, `_settings_from_args`, `_management_headers`, `_healthy_base_url_or_none`, `_proxy_exports`, `_proxy_shell_setup`, `_proxy_eval_hint`, `_load_codex_auth_identity`) in `main.py` or a new `cli/shared.py`
- [ ] Update `main.py` imports to pull handlers from `cli/commands/`
- [ ] Keep `build_parser()` and `main()` in `main.py`
- [ ] Run `python -m compileall src/cdx_proxy_cli_v2/cli/` — no syntax errors
- [ ] Run `cdx --help` and `cdx proxy --help` — still works

## Acceptance Criteria

- [ ] `main.py` is under 250 lines (parser + router + shared helpers)
- [ ] Each `handle_*` lives in its own file
- [ ] `cdx --help`, `cdx proxy --help`, `cdx trace --help` produce correct output
- [ ] No new behavior — pure move refactor

## Rollback

- Revert to original `main.py` from git if anything breaks.
