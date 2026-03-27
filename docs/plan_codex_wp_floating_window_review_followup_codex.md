# Plan: codex_wp Floating Window Review Follow-up (Codex)

## Purpose

Rebase the floating-window follow-up onto the current worktree as observed on 2026-03-27.

This version is stricter about current-state accuracy than the earlier drafts:

1. It separates already-green local fixes from the one still-open blocker.
2. It treats the dirty worktree as the implementation baseline.
3. It targets the current integration failure, not the older startup-timeout failure from prior review snapshots.

## Inputs

- Reviewed drafts:
  - `docs/plan_codex_wp_floating_window_review_followup.md`
  - `docs/plan_codex_wp_floating_window_review_followup_opus.md`
- Current local files:
  - `bin/codex_wp`
  - `src/cdx_proxy_cli_v2/auth/store.py`
  - `src/cdx_proxy_cli_v2/cli/main.py`
  - `src/cdx_proxy_cli_v2/config/settings.py`
  - `src/cdx_proxy_cli_v2/proxy/server.py`
  - `src/cdx_proxy_cli_v2/runtime/singleton.py`
  - `tests/auth/test_keyring_store.py`
  - `tests/config/test_settings.py`
  - `tests/integration/test_cli_runtime_flow.py`
  - `tests/integration/test_codex_wp_green_path.py`
  - `tests/runtime/test_service.py`
  - `tests/runtime/test_singleton.py`
- Repo gates from `AGENTS.md`:
  - touching runtime green-path behavior requires `make test-e2e`
  - touching `bin/codex_wp` prefers `make test-integration-codex-wp` and `make test-e2e`

## Preconditions

- Work from repo root: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- Do not overwrite unrelated dirty changes already present on 2026-03-27.
- Treat the current worktree as the source of truth. The older review drafts describe an earlier branch state.
- Preserve the already-green wrapper-help, upstream `-p` passthrough, singleton replacement, env scoping, and runtime keyring-bypass edits unless new evidence shows one of them is wrong.

## Critical Review

### `docs/plan_codex_wp_floating_window_review_followup.md`

Strengths:

- Good file ownership and repo-gate mapping.
- Good breakdown of the original four review findings.

Gaps:

- It is stale against the live branch.
- It still centers startup and stale-env cleanup as open blockers even though the current focused tests for those areas are now green.
- It does not account for the auth-store / runtime-metadata interaction now blocking `cdx doctor`.

### `docs/plan_codex_wp_floating_window_review_followup_opus.md`

Strengths:

- Strong severity framing.
- Strong operator-safety lens.

Gaps:

- It still spends most of its weight on already-addressed wrapper and singleton issues.
- It does not reconcile with the newer auth-store and env-scoping changes already present in the worktree.
- It does not isolate the current `/health` stall inside a populated runtime auth directory.

### Bottom Line

The earlier drafts remain useful review artifacts, but they are no longer the right execution plan for this branch.

The current branch no longer needs a four-bug implementation queue.

The right next move is:

1. Keep the already-green wrapper, singleton, and env-path fixes intact.
2. Fix auth discovery so runtime metadata JSON is not treated as an auth record.
3. Re-run the integration flows that depend on `cdx doctor` and `codex_wp` green-path runtime behavior.

## Current Verified State

Verified locally on 2026-03-27:

- `pytest -q tests/integration/test_codex_wp_green_path.py -k 'help or profile or floating or pair'`
  - result: `19 passed, 11 deselected`
- `pytest -q tests/runtime/test_singleton.py`
  - result: `5 passed`
- `pytest -q tests/runtime/test_service.py -k 'start_service_removes_stale_auth_dir_from_env_file or does_not_kill_unverified_pid'`
  - result: `2 passed, 20 deselected`
- `pytest -q tests/integration/test_codex_wp_green_path.py -k 'green_path'`
  - result: `1 failed, 29 passed`
  - failure: `cdx doctor --json` timed out while reading `/health`
- `pytest -q tests/integration/test_cli_runtime_flow.py`
  - result: `1 failed`
  - failure: `cdx doctor --json` timed out while reading `/health`

Additional local reproduction on 2026-03-27:

- `fetch_limit_health(auth_dir, base_url=<mock>, prefer_keyring=False)` succeeds quickly before proxy runtime metadata files exist.
- After proxy startup writes `rr_proxy_v2.state.json`, `iter_auth_json_files()` includes that file alongside real auth files.
- `load_auth_records(auth_dir, prefer_keyring=False)` then hangs after encountering the runtime state file because it has no token and still falls through to keyring lookup.

Important code-level implication:

- The remaining blocker is no longer proxy startup.
- The current blocker is auth discovery inside a live runtime auth directory.
- `rr_proxy_v2.state.json` is being treated like an auth candidate, which makes `/health` and `cdx doctor` stall in the runtime path.

## Required Steps

### 1. Preserve the Already-Green Wrapper, Singleton, and Env-Scoping Fixes

Files:

- `bin/codex_wp`
- `src/cdx_proxy_cli_v2/runtime/singleton.py`
- `src/cdx_proxy_cli_v2/config/settings.py`
- `tests/integration/test_codex_wp_green_path.py`
- `tests/runtime/test_singleton.py`
- `tests/runtime/test_service.py`

Required steps:

1. Do not rewrite the current help, profile passthrough, singleton verification, or env-path-scoping logic unless the auth-store fix proves one of them is wrong.
2. Use the currently green focused tests as a guardrail while changing auth discovery.

### 2. Fix Runtime Auth Discovery

Files:

- `src/cdx_proxy_cli_v2/auth/store.py`
- `tests/auth/test_keyring_store.py`
- `tests/integration/test_cli_runtime_flow.py`
- `tests/integration/test_codex_wp_green_path.py`

Required steps:

1. Tighten auth discovery so runtime metadata JSON such as `rr_proxy_v2.state.json` is not treated as an auth file.
2. Ensure non-auth JSON does not trigger keyring lookup in runtime paths.
3. Preserve support for legitimate keyring-backed auth files that contain auth identity metadata but no inline token.
4. Prefer a minimal auth-file classification rule over adding more timeout padding to `cdx doctor`.

Detailed guidance:

- The fix can live either in auth-file iteration or in auth-record classification, but the final behavior must exclude runtime metadata without breaking real keyring-backed auth files.
- Avoid special-casing only the current failure site in `doctor`; fix the shared auth-loading layer instead.
- Preserve the existing `prefer_keyring=False` optimization for real auth records with inline tokens.

### 3. Restore the Integration Green Path

Files:

- `tests/integration/test_cli_runtime_flow.py`
- `tests/integration/test_codex_wp_green_path.py`
- any source files changed while fixing Step 2

Required steps:

1. Re-run the current failing integration commands after the auth-store fix.
2. Confirm that `/health` returns promptly and `cdx doctor --json` succeeds.
3. Confirm that the wrapper multistep proxy flow is green again without changing the already-green wrapper behavior.

## Validation

### Focused Validation During Implementation

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

pytest -q tests/auth/test_keyring_store.py
pytest -q tests/integration/test_cli_runtime_flow.py
pytest -q tests/integration/test_codex_wp_green_path.py -k 'help or profile or floating or pair or green_path'
pytest -q tests/runtime/test_singleton.py
pytest -q tests/runtime/test_service.py -k 'start_service_removes_stale_auth_dir_from_env_file or does_not_kill_unverified_pid'
```

### Required Gates Before Handoff

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

make test-integration-codex-wp
make test-e2e
```

Run the full CLI help sweep only if the final implementation changes CLI help or parser wiring again.

## Output Contract

This follow-up is complete only when all of the following are true:

- current local wrapper help/profile fixes remain green
- current local singleton replacement fixes remain green
- current local env-path-scoping fixes remain green
- runtime metadata JSON is excluded from auth discovery
- non-auth runtime JSON does not trigger keyring lookup
- `tests/integration/test_cli_runtime_flow.py::test_cli_runtime_flow_covers_status_doctor_all_reset_and_trace` passes
- `tests/integration/test_codex_wp_green_path.py::test_codex_wp_green_path_verifies_multistep_proxy_flow` passes
- `make test-integration-codex-wp` passes
- `make test-e2e` passes

## Confidence Loop

### Iteration 1: Prior document

- Confidence: 78%
- Satisfaction: 74%
- Why it failed the gate:
  - it still centered the old startup timeout after the worktree had already moved
  - it did not isolate the `cdx doctor` stall to auth discovery inside a populated runtime auth dir
  - it did not connect the green-path failure to `rr_proxy_v2.state.json` being treated as an auth candidate

### Iteration 2: This plan

- Confidence: 97%
- Satisfaction: 96%
- Why it clears the gate:
  - it is anchored to the currently failing commands, not stale review findings
  - it narrows the live blocker to one concrete auth-store/runtime interaction
  - it maps the minimal code and test changes needed to restore the integration path
  - it keeps the required repo gates explicit before handoff

## Notes

- Preserve the already-green wrapper, singleton, env-scoping, and runtime keyring-bypass changes unless the new auth-store fix proves they need adjustment.
- Prefer filtering non-auth metadata out of auth discovery over adding more timeout padding around `cdx doctor`.
- If the auth-store fix reveals a second independent green-path failure, stop and rebase the plan again on that new evidence.
