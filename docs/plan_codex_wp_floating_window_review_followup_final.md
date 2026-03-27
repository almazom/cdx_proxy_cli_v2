# Plan: codex_wp Floating Window Review Follow-up (Final Canonical)

## Purpose

Provide one branch-accurate, implementation-ready follow-up plan for the current `codex_wp` floating-window worktree as verified on 2026-03-27.

This document replaces the earlier review-oriented drafts as the canonical execution reference for this branch.

It is intentionally stricter than the prior versions:

1. It treats the current dirty worktree as the source of truth.
2. It distinguishes already-green implementation slices from still-necessary handoff steps.
3. It anchors the plan to commands that were re-run locally on 2026-03-27.
4. It keeps enough implementation detail that a developer can either finish the current branch or re-apply the same fixes elsewhere without reopening discovery work.

## Inputs

- Prior drafts:
  - `docs/plan_codex_wp_floating_window_review_followup.md`
  - `docs/plan_codex_wp_floating_window_review_followup_opus.md`
  - `docs/plan_codex_wp_floating_window_review_followup_codex.md`
- Current modified or newly added implementation files:
  - `bin/codex_wp`
  - `src/cdx_proxy_cli_v2/auth/eligibility.py`
  - `src/cdx_proxy_cli_v2/auth/store.py`
  - `src/cdx_proxy_cli_v2/cli/main.py`
  - `src/cdx_proxy_cli_v2/config/settings.py`
  - `src/cdx_proxy_cli_v2/health_snapshot.py`
  - `src/cdx_proxy_cli_v2/proxy/server.py`
  - `src/cdx_proxy_cli_v2/runtime/singleton.py`
  - `tests/auth/test_keyring_store.py`
  - `tests/config/test_settings.py`
  - `tests/integration/test_cli_runtime_flow.py`
  - `tests/integration/test_codex_wp_green_path.py`
  - `tests/runtime/test_service.py`
  - `tests/runtime/test_singleton.py`
- Repository-local gates from `AGENTS.md`:
  - touching `bin/codex_wp` prefers `make test-integration-codex-wp`
  - touching runtime green-path behavior requires `make test-e2e`
  - the full CLI help sweep is preferred when parser wiring or operator-facing help changed

## Preconditions

- Work from repo root: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- Do not overwrite unrelated dirty changes already present in the worktree.
- Treat the live branch as newer than the earlier review snapshots.
- Preserve the already-green behavior unless a fresh failing test proves it is wrong.
- Prefer the smallest change that preserves upstream Codex semantics and current proxy runtime behavior.

## Current Verified State

### Worktree State

Observed on 2026-03-27:

- current branch contains local edits across wrapper, auth loading, runtime singleton, config settings, runtime health, and tests
- the branch is no longer in the same state described by the original four-bug draft
- the active code already contains implementations for:
  - side-effect-free wrapper help handling
  - upstream `-p/--profile` passthrough
  - singleton replacement verification before terminating a PID
  - runtime auth-file filtering and runtime keyring avoidance
  - auth-dir-scoped env-file resolution

### Verified Commands Re-Run On 2026-03-27

Focused tests:

- `pytest -q tests/auth/test_keyring_store.py`
  - result: `10 passed`
- `pytest -q tests/config/test_settings.py`
  - result: `65 passed`
- `pytest -q tests/runtime/test_singleton.py`
  - result: `5 passed`
- `pytest -q tests/runtime/test_service.py`
  - result: `22 passed`
- `pytest -q tests/integration/test_cli_runtime_flow.py`
  - result: `1 passed`
- `pytest -q tests/integration/test_codex_wp_green_path.py -k 'help or profile or floating or pair'`
  - result: `19 passed, 11 deselected`
- `pytest -q tests/integration/test_codex_wp_green_path.py -k green_path`
  - result: `30 passed`

Repo-level gates:

- `make test-integration-codex-wp`
  - result: `30 passed`
- full help sweep
  - commands verified: `cdx --help`, `cdx proxy --help`, `cdx status --help`, `cdx doctor --help`, `cdx stop --help`, `cdx trace --help`, `cdx logs --help`, `cdx limits --help`, `cdx migrate --help`, `cdx reset --help`, `cdx rotate --help`, `cdx all --help`, `cdx run-server --help`
  - result: all listed commands exited successfully
- `make test-e2e`
  - result: `10 passed`

### Current Interpretation

The current branch does not present a reproduced red blocker in the verified wrapper, runtime, CLI, or E2E paths.

The earlier drafts were useful while the branch was still red, but they are no longer the best execution map for the live worktree.

The right follow-up is now:

1. keep the current implementation slices intact
2. review them as a cohesive set
3. re-run the listed gates after any further changes
4. hand off or commit only when the full contract below remains green

## Implementation Slices

### Slice 1: Wrapper Help, Safety, and Upstream Profile Compatibility

Status: implemented locally and green

Owned files:

- `bin/codex_wp`
- `tests/integration/test_codex_wp_green_path.py`

What this slice must guarantee:

1. `--help`, `-h`, and `help` requests are detected before any Zellij side effect.
2. help flows remain side-effect free even when Zellij wrapper flags are present.
3. wrapper help exposes the Zellij-specific surface clearly enough for operators to discover it safely.
4. upstream Codex help still remains visible in wrapper help flows.
5. the wrapper no longer consumes `-p` as a private shortcut.
6. upstream Codex `-p/--profile` passes through unchanged.
7. pair-mode validation does not run before help short-circuiting.

Current implementation signals:

- `bin/codex_wp` now includes explicit help detection via `is_help_request(...)`.
- help detection runs before pair-mode validation and before Zellij launch logic.
- the wrapper parser no longer reserves `-p` as a wrapper-only flag.
- the integration suite contains dedicated help/profile coverage and the full wrapper green path is passing.

If this slice must be re-implemented elsewhere, do it in this order:

1. detect help requests after collecting inner args but before validation or side effects
2. keep wrapper-specific help text separate from inner Codex help text
3. leave all single-letter flags to upstream Codex unless there is a namespaced wrapper-only alternative
4. validate both plain wrapper help and Zellij-flagged help

Primary acceptance checks:

- `bin/codex_wp --zellij-floating --help` has no Zellij side effect
- `bin/codex_wp --zellij-new-tab --help` has no Zellij side effect
- `bin/codex_wp --zellij-floating-pair --help` has no Zellij side effect
- `bin/codex_wp exec -p test-profile --help` succeeds
- `bin/codex_wp review -p test-profile --help` succeeds

### Slice 2: Safe `cdx trace --replace` Singleton Replacement

Status: implemented locally and green

Owned files:

- `src/cdx_proxy_cli_v2/runtime/singleton.py`
- `src/cdx_proxy_cli_v2/cli/main.py`
- `tests/runtime/test_singleton.py`

What this slice must guarantee:

1. a live PID in the trace pid file is not enough to justify termination
2. replacement is allowed only when the live PID matches the expected `cdx trace` process shape
3. unrelated reused PIDs are not terminated
4. stale dead pid files are still cleaned up
5. low-level singleton helpers do not unilaterally `sys.exit()`
6. CLI callers decide exit behavior and error messaging

Current implementation signals:

- `singleton_lock(...)` accepts an optional `process_matches` verifier
- `is_expected_trace_process(...)` validates a live trace PID against command-line shape and active auth dir
- `handle_trace(...)` catches `SingletonLockError` and returns a controlled CLI exit code

If this slice must be re-implemented elsewhere, do it in this order:

1. keep pid-file cleanup for stale dead PIDs
2. add explicit process verification before kill-on-replace
3. surface failures as exceptions or structured errors, not direct process exit
4. wire CLI callers to print operator-facing diagnostics and exit non-zero

Primary acceptance checks:

- stale pid file is removed and lock acquisition succeeds
- live unverified PID is not killed
- verified trace PID can be replaced when `--replace` is used
- trace command without `--replace` still blocks concurrent live instances

### Slice 3: Runtime Auth Discovery and Keyring Behavior

Status: implemented locally and green

Owned files:

- `src/cdx_proxy_cli_v2/auth/store.py`
- `src/cdx_proxy_cli_v2/auth/eligibility.py`
- `src/cdx_proxy_cli_v2/health_snapshot.py`
- `src/cdx_proxy_cli_v2/proxy/server.py`
- `tests/auth/test_keyring_store.py`
- `tests/integration/test_cli_runtime_flow.py`
- `tests/integration/test_codex_wp_green_path.py`

What this slice must guarantee:

1. runtime metadata JSON such as `rr_proxy_v2.state.json` is not treated as an auth record
2. runtime paths do not block on unnecessary keyring lookups when a real file token already exists
3. legitimate keyring-backed auth metadata still loads correctly when no inline token exists
4. the fix lives in shared auth-loading behavior, not as a narrow `doctor`-only workaround
5. proxy runtime health, doctor, and wrapper green-path flows stay fast and deterministic

Current implementation signals:

- `load_auth_records(..., prefer_keyring=...)` now filters payloads through `_looks_like_auth_record(...)`
- `ProxyRuntime`, `health_snapshot`, and `fetch_limit_health(...)` now pass `prefer_keyring=False` on runtime paths
- runtime-only JSON no longer qualifies as an auth record unless it resembles one structurally
- integration flows covering `status`, `doctor`, `all`, `/responses`, and wrapper multistep proxy use are green

If this slice must be re-implemented elsewhere, do it in this order:

1. classify auth-like JSON before any keyring call
2. skip runtime metadata files that do not expose auth identity or token-like fields
3. preserve keyring-backed auth files that carry enough auth identity to be legitimate records
4. push `prefer_keyring=False` only through runtime and proxy health paths, not through unrelated user-facing auth workflows unless intended

Primary acceptance checks:

- runtime state JSON is ignored during auth loading
- runtime auth loading skips unnecessary keyring calls when file tokens already exist
- keyring-backed auth metadata still resolves a token correctly
- `cdx doctor --json` succeeds against a live runtime auth dir
- `test_codex_wp_green_path_verifies_multistep_proxy_flow` passes

### Slice 4: Auth-Dir-Scoped Env-File Resolution

Status: implemented locally and green

Owned files:

- `src/cdx_proxy_cli_v2/config/settings.py`
- `tests/config/test_settings.py`
- `tests/runtime/test_service.py`

What this slice must guarantee:

1. an inherited env file from another auth dir does not silently redirect the active runtime
2. explicit env files still work when they are intentionally provided
3. auth-dir-specific `.env` handling remains local to the resolved auth dir
4. stale `CLIPROXY_AUTH_DIR` entries do not survive successful runtime startup

Current implementation signals:

- `scoped_env_file_path(...)` rejects inherited env files that do not resolve under the active auth dir
- `build_settings(...)` and `load_codex_wp_defaults(...)` now distinguish explicit env-file usage from inherited env-file usage
- runtime service tests verify stale auth-dir env cleanup
- config tests verify mismatched inherited env files are ignored for the active auth dir

If this slice must be re-implemented elsewhere, do it in this order:

1. resolve the active auth dir first
2. accept only explicit env files globally
3. treat inherited env-file paths as valid only when they are scoped under the active auth dir
4. keep the auth-dir `.env` as the fallback default

Primary acceptance checks:

- mismatched inherited env file is ignored
- auth-dir-scoped env file does not redirect runtime unexpectedly
- runtime startup removes stale `CLIPROXY_AUTH_DIR` from `.env`

## Required Steps

### Step 1: Treat This Document as the Single Active Plan

Actions:

1. stop using the older three drafts as execution references for this branch
2. keep them only as review history
3. use this file for any remaining implementation, review, validation, or handoff work

Why:

- the earlier drafts target an older branch state
- this branch is already green on the known critical paths
- continued execution from an outdated plan would risk reopening solved work

### Step 2: Audit the Current Diff Before Any New Edits

Actions:

1. review the diff for the owned files in Slices 1 through 4
2. verify there is no accidental behavior outside the intended scope
3. preserve unrelated dirty changes outside these slices
4. do not collapse or rewrite working logic just to make the diff smaller

Audit focus:

- wrapper parser ordering and help short-circuiting
- singleton replacement safety and CLI error handling
- auth-record classification and runtime `prefer_keyring=False` plumbing
- env-file scoping and cleanup semantics
- test additions that directly prove the intended behavior

### Step 3: Make Further Code Changes Only If One of These Conditions Is True

Change code only if:

1. a newly re-run gate fails
2. diff audit shows behavior drift outside the intended scope
3. review of the current edits finds a correctness issue, hidden regression risk, or unclear operator contract

Otherwise:

- treat implementation as locally complete
- move directly to verification and handoff

### Step 4: If A Regression Reappears, Use Slice-Based Repair Instead of Broad Replanning

Use this routing table:

- help, Zellij, or profile passthrough failure:
  - repair Slice 1
- `cdx trace --replace` safety failure:
  - repair Slice 2
- `doctor`, `/health`, runtime auth loading, or keyring stall failure:
  - repair Slice 3
- env inheritance, auth-dir redirection, or stale `.env` behavior failure:
  - repair Slice 4

Rule:

- make the smallest repair in the owning slice
- rerun the focused tests for that slice
- rerun `make test-integration-codex-wp` and `make test-e2e` before handoff

### Step 5: Handoff Only After Re-Running the Required Gates On the Final Diff

Required focused checks:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

pytest -q tests/auth/test_keyring_store.py
pytest -q tests/config/test_settings.py
pytest -q tests/runtime/test_singleton.py
pytest -q tests/runtime/test_service.py
pytest -q tests/integration/test_cli_runtime_flow.py
pytest -q tests/integration/test_codex_wp_green_path.py -k 'help or profile or floating or pair'
pytest -q tests/integration/test_codex_wp_green_path.py -k green_path
```

Required repo gates:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

make test-integration-codex-wp
make test-e2e
```

High-confidence operator sweep:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

cdx --help
cdx proxy --help
cdx status --help
cdx doctor --help
cdx stop --help
cdx trace --help
cdx logs --help
cdx limits --help
cdx migrate --help
cdx reset --help
cdx rotate --help
cdx all --help
cdx run-server --help
```

## Validation Rules

Mark the branch as `blocked` if any of the following become true:

- wrapper help triggers Zellij side effects again
- upstream `-p/--profile` semantics are consumed by wrapper parsing again
- trace replacement can kill an unverified live PID
- runtime auth loading includes non-auth metadata files again
- runtime paths hang on keyring access or auth discovery
- auth-dir env inheritance can redirect runtime state outside the active auth dir
- `make test-integration-codex-wp` fails
- `make test-e2e` fails

Mark the branch as `revise` if:

- all gates pass but code review finds unnecessary complexity or weak naming
- tests are green but one slice lacks direct coverage for the intended contract
- operator help text is correct but unclear enough to slow discovery or future maintenance

Mark the branch as `pass` only when:

- all owned slices remain green
- focused tests remain green
- repo gates remain green
- help sweep remains green
- no new diff audit finding suggests hidden scope creep

## Output Contract

This follow-up is complete only when all of the following are true:

- side-effect-free wrapper help remains intact
- upstream `-p/--profile` passthrough remains intact
- `cdx trace --replace` refuses to kill unverified reused PIDs
- runtime metadata JSON is excluded from auth discovery
- runtime health and doctor flows no longer stall on keyring or metadata noise
- auth-dir-scoped env handling remains intact
- `tests/auth/test_keyring_store.py` passes
- `tests/config/test_settings.py` passes
- `tests/runtime/test_singleton.py` passes
- `tests/runtime/test_service.py` passes
- `tests/integration/test_cli_runtime_flow.py` passes
- `tests/integration/test_codex_wp_green_path.py` focused help/profile/pair checks pass
- `tests/integration/test_codex_wp_green_path.py -k green_path` passes
- `make test-integration-codex-wp` passes
- `make test-e2e` passes
- the listed CLI help commands exit successfully

## Confidence Loop

### Iteration 1: Original Four-Bug Draft

- Confidence: 68%
- Satisfaction: 66%
- Why it no longer clears the gate:
  - it assumed the branch was still red in wrapper and startup paths
  - it did not reflect the implementation already present in the worktree
  - it over-focused on problems that are now green locally

### Iteration 2: Branch-Rebased Codex Draft

- Confidence: 88%
- Satisfaction: 86%
- Why it improved:
  - it rebased onto the then-current dirty worktree
  - it identified runtime auth discovery as the active blocker at that point
  - it narrowed the live failure much better than the older drafts
- Why it still did not become canonical:
  - its failure snapshot became stale after the branch moved again
  - it still described the work as partially red after the known gates were repaired

### Iteration 3: This Final Canonical Plan

- Confidence: 99%
- Satisfaction: 98%
- Why it clears the 95%+ readiness bar:
  - it is tied to the live worktree on 2026-03-27
  - it is backed by exact focused test, integration, help-sweep, and E2E results
  - it maps the implemented behavior into four explicit ownership slices
  - it gives a direct fallback path if any slice regresses later
  - it avoids stale problem framing and treats the branch as implementation-complete unless a fresh gate reopens work

## Notes

- For this branch, the most likely next action is not broad implementation. It is diff audit, final verification, and handoff.
- If a future edit reopens one of the known regressions, repair only the owning slice instead of returning to a full branch-wide replanning pass.
- Keep this document as the canonical follow-up plan unless a new failing gate produces newer evidence than the 2026-03-27 command set recorded here.
