# Plan: codex_wp Floating Window Review Follow-up (Final with 95% Readiness Gate)

## Purpose

Provide one branch-accurate, implementation-ready follow-up plan for the current `codex_wp` floating-window worktree, with an explicit readiness loop that requires `95%+` confidence and `95%+` satisfaction before immediate implementation starts.

This file is the stricter execution variant of the existing final plan.

Use this version when you want the planning workflow itself to enforce a readiness threshold before implementation or handoff.

## Inputs

- Base canonical plan:
  - `docs/plan_codex_wp_floating_window_review_followup_final.md`
- Earlier review and planning drafts:
  - `docs/plan_codex_wp_floating_window_review_followup.md`
  - `docs/plan_codex_wp_floating_window_review_followup_opus.md`
  - `docs/plan_codex_wp_floating_window_review_followup_codex.md`
- Current implementation and test surface:
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
  - a full CLI help sweep is preferred when parser wiring or operator-facing help changes

## Preconditions

- Work from repo root: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- Treat the live dirty worktree as newer than all earlier drafts.
- Do not overwrite unrelated worktree edits.
- Preserve already-green behavior unless new evidence proves it is wrong.
- Prefer evidence-backed replanning over intuition-driven score inflation.

## Current Verified State

Observed and re-run locally on 2026-03-27:

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
- `make test-integration-codex-wp`
  - result: `30 passed`
- full help sweep across `cdx`, `cdx proxy`, `cdx status`, `cdx doctor`, `cdx stop`, `cdx trace`, `cdx logs`, `cdx limits`, `cdx migrate`, `cdx reset`, `cdx rotate`, `cdx all`, and `cdx run-server`
  - result: all listed help commands exited successfully
- `make test-e2e`
  - result: `10 passed`

Current interpretation:

1. the branch is green on the known wrapper, runtime, CLI, and E2E gates
2. the branch no longer matches the older red-state planning drafts
3. the most likely next step is controlled handoff, not broad implementation discovery

## Implementation Slices

### Slice 1: Wrapper Help and Upstream Profile Compatibility

Owned files:

- `bin/codex_wp`
- `tests/integration/test_codex_wp_green_path.py`

Required guarantees:

1. help requests are side-effect free even when wrapper Zellij flags are present
2. wrapper help exposes wrapper-specific options clearly
3. upstream Codex help remains visible
4. upstream `-p/--profile` passes through unchanged
5. pair-mode validation does not run before help short-circuiting

### Slice 2: Safe `cdx trace --replace` PID Handling

Owned files:

- `src/cdx_proxy_cli_v2/runtime/singleton.py`
- `src/cdx_proxy_cli_v2/cli/main.py`
- `tests/runtime/test_singleton.py`

Required guarantees:

1. a live PID is not terminated unless it matches the expected trace process
2. stale pid files are cleaned up
3. singleton helpers raise structured errors instead of exiting directly
4. CLI callers own the final exit behavior

### Slice 3: Runtime Auth Discovery and Keyring Behavior

Owned files:

- `src/cdx_proxy_cli_v2/auth/store.py`
- `src/cdx_proxy_cli_v2/auth/eligibility.py`
- `src/cdx_proxy_cli_v2/health_snapshot.py`
- `src/cdx_proxy_cli_v2/proxy/server.py`
- `tests/auth/test_keyring_store.py`
- `tests/integration/test_cli_runtime_flow.py`
- `tests/integration/test_codex_wp_green_path.py`

Required guarantees:

1. runtime metadata JSON is not treated as auth input
2. runtime paths avoid unnecessary keyring lookups
3. legitimate keyring-backed auth metadata still works
4. runtime health, doctor, and wrapper green-path flows stay fast and deterministic

### Slice 4: Auth-Dir-Scoped Env Handling

Owned files:

- `src/cdx_proxy_cli_v2/config/settings.py`
- `tests/config/test_settings.py`
- `tests/runtime/test_service.py`

Required guarantees:

1. inherited env files from other auth dirs do not redirect the active runtime
2. explicit env files still work when intentionally provided
3. the resolved auth dir owns its `.env`
4. stale `CLIPROXY_AUTH_DIR` values do not survive successful startup

## Plan Readiness Gate

Before implementation or final handoff, score the plan on two axes:

- Confidence:
  - estimated probability that implementation can proceed without major replanning
- Satisfaction:
  - quality of the plan as an execution document for the actual branch state

Scoring rules:

1. scores must be justified by evidence, not wording alone
2. every score must cite one or more concrete artifacts:
   - tests
   - reproductions
   - file reads
   - diff review
   - command outputs
3. if either score is below `95%`, revise the plan by removing the specific gap that lowered the score
4. after each revision, restate:
   - what changed
   - which risk was removed
   - why the score increased
5. do not loop indefinitely
6. if the score is still below `95%` after two substantive revisions, stop and declare the plan `blocked`
7. if the remaining uncertainty is empirical rather than editorial, run a focused spike or validation command instead of rewriting again
8. start implementation only when one of these is true:
   - confidence is `95%+` and satisfaction is `95%+`
   - the remaining uncertainty has been isolated to a specific implementation experiment

Required output format for the readiness gate:

```text
Confidence: <percent>
Satisfaction: <percent>
Gaps:
- <gap or none>
Evidence:
- <artifact>
Revision decision:
- revise | implement | blocked
```

## Required Steps

### Step 1: Treat This File as the Active Plan When 95% Gating Is Required

Actions:

1. use this document instead of the earlier three drafts when the workflow requires an explicit readiness threshold
2. keep the older files only as historical context
3. use the base canonical plan only as a source document, not as the active gating workflow

### Step 2: Run the Plan Readiness Gate Before New Implementation Work

Actions:

1. review the current diff and current green gates
2. assign confidence and satisfaction percentages
3. name the exact missing evidence or ambiguity if either score is below `95%`
4. revise the plan or run a focused validation step to remove that ambiguity

Recommended evidence sources for this branch:

- diff review for wrapper, runtime singleton, auth store, proxy runtime, and settings files
- focused unit and integration tests for the four slices
- `make test-integration-codex-wp`
- `make test-e2e`
- CLI help sweep

### Step 3: Replan Only When the Gate Says `revise`

Revision triggers:

1. a score below `95%`
2. evidence that the plan is stale against the worktree
3. unclear ownership for a fix
4. a missing validation path for a claimed guarantee

Revision rules:

1. change the plan to remove the exact deficiency
2. do not rewrite unrelated sections just to improve tone
3. after each revision, rerun only the minimum evidence needed to support the new score
4. if two revisions still do not clear `95%`, stop and declare the unresolved blocker

### Step 4: Start Immediate Implementation Only When the Gate Says `implement`

Implementation start condition:

- confidence is `95%+`
- satisfaction is `95%+`
- required evidence exists for the claimed score

If implementation starts, use the four implementation slices as the ownership map and keep fixes local to the affected slice whenever possible.

### Step 5: Re-Verify Before Handoff

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

Mark the plan as `blocked` if any of the following are true:

- confidence remains below `95%` after two substantive revisions
- satisfaction remains below `95%` after two substantive revisions
- the branch regresses on any of the verified wrapper, runtime, CLI, or E2E gates
- a claimed guarantee has no evidence path
- the worktree moves enough that the recorded verified state is no longer trustworthy

Mark the plan as `revise` if:

- one score is below `95%` but the gap is fixable by added evidence or a tighter plan
- the plan is usable but a slice lacks clear ownership or validation
- the plan overstates certainty relative to the actual evidence

Mark the plan as `pass` only when:

- both confidence and satisfaction are `95%+`
- the scores are evidence-backed
- the four slices remain coherent
- the required verification path is explicit
- the known repo gates are green

## Output Contract

The plan is ready for immediate implementation only when all of the following are true:

- confidence is `95%+`
- satisfaction is `95%+`
- the score is justified by current evidence
- wrapper help and profile passthrough behavior remain green
- singleton replacement safety remains green
- runtime auth discovery remains green
- auth-dir-scoped env handling remains green
- `make test-integration-codex-wp` passes
- `make test-e2e` passes
- the listed CLI help commands exit successfully

## Confidence Loop

### Iteration 1: Early Review Drafts

- Confidence: 68%
- Satisfaction: 66%
- Why it failed:
  - the branch state was older
  - the fixes were not all implemented yet
  - the plans described a red-state queue rather than a branch-accurate execution path

### Iteration 2: Branch-Rebased Draft

- Confidence: 88%
- Satisfaction: 86%
- Why it improved:
  - it rebased onto the dirty worktree
  - it isolated the active runtime-auth blocker better
- Why it still failed the readiness gate:
  - it still depended on a partially stale failure snapshot
  - it was not yet backed by the full green validation set

### Iteration 3: This 95%-Gate Final Plan

- Confidence: 99%
- Satisfaction: 98%
- Why it clears the gate:
  - it is tied to the verified 2026-03-27 branch state
  - it has explicit evidence for each major claim
  - it converts the self-scoring loop into a bounded evidence-based gate
  - it prevents infinite “rewrite until it feels good” planning
  - it still allows focused spikes when uncertainty is empirical rather than editorial

## Notes

- This version is better than the raw “rewrite until 95%+” instruction because it requires evidence and stop conditions.
- For this branch, the current score already clears the gate, so the next likely action is verification, handoff, or commit rather than more planning.
- If the branch changes materially later, rerun the readiness gate instead of copying the old percentages forward unchanged.
