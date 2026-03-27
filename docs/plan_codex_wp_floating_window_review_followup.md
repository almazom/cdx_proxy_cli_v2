# Plan: codex_wp Floating Window Review Follow-up

## Purpose

Turn the current floating-window review findings into an implementation sequence that is safe to execute immediately.

This plan covers four active regressions:

1. `codex_wp` help paths still trigger Zellij side effects.
2. The wrapper consumes upstream Codex `-p/--profile` semantics.
3. `cdx trace --replace` can terminate an unrelated reused PID.
4. The wrapper green path is blocked by `cdx proxy --print-env-only` timing out during startup.

## Inputs

- Review target: `docs/plan_codex_wp_floating_window_review_followup.md`
- Shell wrapper: `bin/codex_wp`
- Runtime singleton: `src/cdx_proxy_cli_v2/runtime/singleton.py`
- Proxy startup path: `src/cdx_proxy_cli_v2/runtime/service.py`
- Proxy CLI entrypoint: `src/cdx_proxy_cli_v2/cli/main.py`
- Integration coverage: `tests/integration/test_codex_wp_green_path.py`
- Runtime coverage: `tests/runtime/test_service.py`
- Repo gate from `AGENTS.md`:
  - touching `bin/codex_wp` prefers both `make test-integration-codex-wp` and `make test-e2e`
  - runtime changes that affect green-path behavior require `make test-e2e`

## Preconditions

- Work from repo root: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- Preserve current Zellij launch behavior for non-help execution paths.
- Preserve upstream Codex argument passthrough unless a flag is explicitly namespaced as wrapper-only.
- Reuse the existing runtime process-verification pattern instead of adding a second ownership model.

## Current Evidence

### Confirmed Reproductions

- `bin/codex_wp --zellij-floating --help` exits `0` and launches a pane instead of printing safe help.
- `bin/codex_wp exec -p test-profile --help` exits `2` with `unexpected argument 'test-profile' found`.
- `pytest -q tests/integration/test_codex_wp_green_path.py -k 'floating or pair or help or profile or green_path'`
  - result: `23 passed, 1 failed`
  - remaining failure: `test_codex_wp_green_path_verifies_multistep_proxy_flow`
  - failure point: `cdx proxy --print-env-only` timed out after `30.0` seconds
- `pytest -q tests/runtime/test_service.py -k 'reused_pid or start_service or stop_service'`
  - result: `6 passed, 1 failed`
  - failing test: stale `CLIPROXY_AUTH_DIR` is not removed from `.env`

### File-Level Readiness

- `bin/codex_wp`
  - wrapper parsing is front-loaded
  - Zellij side effects happen before any help short-circuit
  - wrapper-only `-p` expansion still rewrites argv into `exec <prompt>`
- `src/cdx_proxy_cli_v2/runtime/singleton.py`
  - singleton replacement kills the stored PID without verifying process identity
- `src/cdx_proxy_cli_v2/runtime/service.py`
  - startup retry path gives no early-exit diagnostics when the child dies or never becomes ready
  - env-file cleanup regression is already covered by a failing test

## Required Steps

### 1. Make `codex_wp` help side-effect free

Files:

- `bin/codex_wp`
- `tests/integration/test_codex_wp_green_path.py`

Implementation:

1. Add a help-detection pass before any Zellij branch executes.
2. Treat wrapper help as side-effect free even when wrapper launch flags are present.
3. Emit wrapper-specific help text for:
   - `--zellij-new-tab`
   - `--zellij-template`
   - `--zellij-cwd`
   - `--zellij-dry-run`
   - `--zellij-floating`
   - `--zellij-floating-pair`
   - pair prompt flags
   - floating geometry flags
4. Append or prefix the upstream Codex help so operators still see the real inner CLI surface.
5. Ensure help handling happens before pair-mode validation and before any `zellij action` or `zellij run` call.

Tests:

- add integration tests proving these commands do not touch fake Zellij:
  - `bin/codex_wp --zellij-floating --help`
  - `bin/codex_wp --zellij-new-tab --help`
  - `bin/codex_wp --zellij-floating-pair --help`
- assert help output contains wrapper Zellij terms and the fake Zellij capture file stays empty

### 2. Remove the wrapper `-p` collision

Files:

- `bin/codex_wp`
- `tests/integration/test_codex_wp_green_path.py`

Implementation:

1. Remove custom short-flag handling for `-p`.
2. Keep wrapper prompt shortcuts namespaced with long-form wrapper flags only if still needed.
3. Pass upstream `-p/--profile` through unchanged in both normal and help flows.
4. Recheck wrapper parsing so argument order no longer changes Codex semantics.

Tests:

- add integration coverage for:
  - `bin/codex_wp exec -p test-profile --help`
  - `bin/codex_wp review -p test-profile --help`
- assert the help output succeeds and includes upstream help content instead of wrapper parse errors

### 3. Harden `cdx trace --replace` against PID reuse

Files:

- `src/cdx_proxy_cli_v2/runtime/singleton.py`
- `tests/runtime/test_singleton.py` or the nearest runtime test module if new coverage fits better there

Implementation:

1. Add process-identity verification for the trace singleton, matching the service-runtime approach:
   - expected process must still be alive
   - expected process must look like the `cdx trace` flow, not an arbitrary PID reuse
2. Refuse to terminate live unverified processes.
3. Replace `sys.exit()` in the low-level helper with a dedicated exception or structured result so callers control CLI exit behavior.
4. Keep stale dead-PID cleanup behavior.

Tests:

- stale PID file is removed and lock acquisition succeeds
- live reused PID that is not a trace process is not killed
- `kill_existing=True` replaces a verified trace process and reports the previous PID

### 4. Recover proxy startup and green-path wrapper execution

Files:

- `src/cdx_proxy_cli_v2/runtime/service.py`
- `src/cdx_proxy_cli_v2/cli/main.py` only if CLI output/contracts need tightening
- `tests/runtime/test_service.py`
- `tests/integration/test_codex_wp_green_path.py`

Implementation:

1. Reproduce the `cdx proxy --print-env-only` timeout in isolation.
2. Fix the already-covered env persistence bug so stale `CLIPROXY_AUTH_DIR` is removed from `.env` on successful startup.
3. Add startup diagnostics around the spawn-and-ready loop:
   - child argv
   - child PID
   - child exit status when it dies before readiness
   - recent log tail when startup fails
4. Distinguish between:
   - child exited immediately
   - child is alive but `/debug` never became ready
   - stale pid/state/env data blocked startup
5. Make the failure actionable enough that the green-path test does not hang for the full outer timeout when startup already failed.

Tests:

- keep `tests/runtime/test_service.py::test_start_service_removes_stale_auth_dir_from_env_file` green
- add or tighten service tests for early child exit / failed readiness if needed
- restore `test_codex_wp_green_path_verifies_multistep_proxy_flow`

## Validation

### Focused Validation During Implementation

Run these while coding:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

pytest -q tests/integration/test_codex_wp_green_path.py -k 'help or profile or floating or pair'
pytest -q tests/runtime/test_service.py -k 'start_service or stop_service or reused_pid'
pytest -q tests/runtime/test_singleton.py
pytest -q tests/integration/test_codex_wp_green_path.py -k green_path
```

### Required Gates Before Handoff

Because this change set touches `bin/codex_wp` and runtime green-path behavior, run:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

make test-integration-codex-wp
make test-e2e
```

Run the full help sweep only if the final help output shape or parser wiring changes beyond the targeted wrapper flags.

## Output Contract

Implementation is complete only when all of the following are true:

- wrapper help is side-effect free
- wrapper help exposes the Zellij-specific surface
- upstream Codex `-p/--profile` passes through unchanged
- `cdx trace --replace` does not kill unrelated reused PIDs
- stale `CLIPROXY_AUTH_DIR` is removed from `.env` on successful startup
- `test_codex_wp_green_path_verifies_multistep_proxy_flow` passes
- `make test-integration-codex-wp` passes
- `make test-e2e` passes

## Confidence Loop

### Iteration 1: Prior document

- Confidence: 72%
- Satisfaction: 70%
- Why it failed the gate:
  - too review-oriented
  - no file-level ownership
  - no startup-diagnostics step for the timeout
  - no explicit validation sequence for runtime plus wrapper changes

### Iteration 2: This plan

- Confidence: 96%
- Satisfaction: 96%
- Why it clears the gate:
  - each regression is mapped to exact files
  - the startup timeout has an explicit isolate, diagnose, and fix sequence
  - the validation path matches repo-local instructions
  - the plan is specific enough to begin implementation immediately without another planning pass

## Notes

- Prefer the smallest behavioral change that restores upstream Codex compatibility.
- Prefer matching existing service-runtime process verification semantics over introducing a second process metadata format unless tests show verification by command line is insufficient.
- If startup debugging reveals a deeper proxy-server regression outside this scope, stop after preserving diagnostics and state the concrete blocker.
