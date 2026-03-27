# Plan: codex_wp Floating Window Review Follow-up (Ready to Implementation)

## Purpose

Provide one branch-accurate, implementation-ready plan that merges:

- the strict self-QA and risk-triage flow from `docs/plan_codex_wp_floating_window_review_followup_qa_final.md`
- the concrete claim inventory, fresh verification summary, and readiness conclusion from `docs/plan_codex_wp_floating_window_review_followup_qa_final_opus.md`

Use this file as the active plan for any further implementation, validation, handoff, or commit decision on the floating-window follow-up work.

## Inputs

- Source plans:
  - `docs/plan_codex_wp_floating_window_review_followup_qa_final.md`
  - `docs/plan_codex_wp_floating_window_review_followup_qa_final_opus.md`
- Current implementation surface:
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
  - touching proxy/runtime green-path behavior requires `make test-e2e`
  - touching CLI command surface or help text prefers the full help sweep

## Preconditions

- Work from repo root: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- Treat the live worktree as newer than historical drafts.
- Do not overwrite unrelated user edits.
- Preserve already-green behavior unless fresh evidence proves otherwise.
- Do not carry forward confidence scores blindly if the worktree changed materially after March 27, 2026.
- If the branch no longer matches the verified state below, rerun the relevant slice checks before treating this plan as ready.

## Current Verified State

The strongest shared conclusion across both source plans is:

- the four implementation slices are already implemented on the reviewed branch state
- no open blocking gaps were left after evidence-based review
- the branch cleared unit, integration, wrapper, CLI-help, and E2E gates on March 27, 2026

Fresh verification captured in the source plans:

| Gate | Result |
|------|--------|
| `pytest -q tests/auth/test_keyring_store.py` | 10 passed |
| `pytest -q tests/config/test_settings.py` | 65 passed |
| `pytest -q tests/runtime/test_singleton.py` | 5 passed |
| `pytest -q tests/runtime/test_service.py` | 22 passed |
| `pytest -q tests/integration/test_cli_runtime_flow.py` | 1 passed |
| `pytest -q tests/integration/test_codex_wp_green_path.py -k 'help or profile or floating or pair'` | 19 passed, 11 deselected |
| `pytest -q tests/integration/test_codex_wp_green_path.py -k green_path` | 30 passed |
| `make test-integration-codex-wp` | 30 passed |
| Full CLI help sweep across 13 `cdx` commands | all exited 0 |
| `make test-e2e` | 10 passed |

Operational interpretation:

1. if the current worktree still matches that reviewed branch state, the next step is controlled handoff or commit, not exploratory replanning
2. if new edits are introduced, use the slice and verification rules below to keep the branch implementation-ready
3. if a new gap appears, use the self-QA flow before scoring readiness again

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

Evidence anchors from the reviewed branch:

- wrapper help detection runs before Zellij and pair-mode processing
- wrapper help text documents wrapper-only options separately from upstream behavior
- green-path integration coverage includes help, profile, floating-window, and pair-mode scenarios

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

Evidence anchors from the reviewed branch:

- trace replacement verifies process identity before termination
- stale pid cleanup is covered in singleton lifecycle logic
- singleton lock failures are surfaced as structured errors and converted to CLI exit behavior in the command layer

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

Evidence anchors from the reviewed branch:

- proxy runtime call sites opt out of unnecessary keyring lookup on internal paths
- auth store logic still supports intentional keyring-backed metadata
- integration flow remains green without requiring keyring availability

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

Evidence anchors from the reviewed branch:

- auth-dir resolution scopes `.env` loading to the active auth directory
- explicitly supplied env files still take precedence when intentionally passed
- tests cover stale auth-dir values and confirm they do not redirect startup

## Required Steps

### Step 1: Use This File as the Active Plan

Rules:

1. treat this file as the single active implementation and handoff plan for this follow-up work
2. keep the two source plans as supporting references, not as competing execution documents
3. use the live worktree as the truth source if it diverges from either source plan

### Step 2: Confirm Whether Work Is Already Ready

Decision rule:

1. if the current branch still satisfies all four slice guarantees and no new gaps are visible, skip directly to Step 7
2. if any slice guarantee is uncertain, continue with Steps 3 through 6
3. if the branch changed materially since March 27, 2026, do not reuse prior readiness scores without rerunning the relevant checks

### Step 3: Build the Claim Inventory

For each affected slice, record:

- the behavior claim
- the safety claim
- the scope claim
- the verification claim
- the owning files and tests

Minimum questions for each claim:

1. what evidence proves it
2. what would make it false
3. what dependency it relies on
4. what remains unknown
5. what breaks if it is false

### Step 4: Discover and Close Gaps with Evidence

Gap types:

- `evidence_missing`
- `stale_evidence`
- `unclear_owner`
- `missing_validation`
- `risky_assumption`
- `conflicting_requirement`
- `unclear_recovery`

Allowed closure methods:

- file evidence
- diff review
- focused unit tests
- focused integration tests
- targeted reproductions
- CLI help checks
- repo-level gates already required by this plan

Rules:

1. close gaps with evidence, not intuition
2. keep unresolved gaps open if no evidence path exists yet
3. if one focused experiment can close a gap, record that exact next action

### Step 5: Score Residual Risk

Score each unresolved gap on `Impact`, `Likelihood`, `Detectability`, `Scope`, and `Recovery` using `1..5`.

Use:

```text
Blocking Probability % =
(
  0.30 * Impact +
  0.25 * Likelihood +
  0.20 * Scope +
  0.15 * Detectability +
  0.10 * Recovery
) / 5 * 100
```

Action thresholds:

- `0%` to `24%`: continue
- `25%` to `49%`: continue with mitigation
- `50%` to `69%`: run one focused gap-closure check before scoring readiness
- `70%` to `84%`: pause the affected slice
- `85%` to `100%`: stop the broader flow and escalate immediately

### Step 6: Apply Verification by Changed Surface

Run the minimum checks that match the actual edit scope.

If Slice 1 changes:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

pytest -q tests/integration/test_codex_wp_green_path.py -k 'help or profile or floating or pair'
make test-integration-codex-wp
```

Add these when CLI help or wrapper entry behavior changed:

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

If Slice 2 changes:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

pytest -q tests/runtime/test_singleton.py
```

If Slice 3 changes:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

pytest -q tests/auth/test_keyring_store.py
pytest -q tests/integration/test_cli_runtime_flow.py
pytest -q tests/integration/test_codex_wp_green_path.py -k green_path
```

If Slice 4 changes:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

pytest -q tests/config/test_settings.py
pytest -q tests/runtime/test_service.py
```

Run repo gates when the change touches runtime behavior, operator green paths, proxy behavior, or `bin/codex_wp`:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

make test-integration-codex-wp
make test-e2e
```

### Step 7: Run the Readiness Gate

Only score readiness after claim extraction, gap closure attempts, risk scoring, and required verification are complete.

Rules:

1. if any unresolved gap is `85%+`, decision is `stop-factory`
2. if any unresolved gap is `70%` to `84%`, decision is `pause-lane`
3. if any unresolved gap is `50%` to `69%`, decision is `revise`
4. if no unresolved gap is above `49%` and all required checks are green, decision may be `implement`
5. if the branch is already green and no new code change is needed, decision may be `handoff-or-commit`

### Step 8: Handoff Cleanly

Before handoff:

1. state which slices changed
2. list the exact checks run
3. report any open gaps or say `none`
4. report whether the branch is ready for implementation, ready for handoff, or blocked

## Validation Rules

Mark the result as `blocked` if any of the following are true:

- any unresolved gap has `85%+` blocking probability
- a claimed guarantee has no evidence path
- the branch regresses on any required verified gate
- the worktree changed enough that the recorded verified state is no longer trustworthy and revalidation was skipped

Mark the result as `revise` if:

- one or more gaps remain in the `50%` to `84%` range
- a slice guarantee is plausible but still weakly evidenced
- slice ownership or validation scope is unclear

Mark the result as `pass` only when:

- no unresolved gap remains above `49%`
- required checks for the changed surface are green
- the four slices remain coherent
- the implementation or handoff decision is backed by evidence

## Output Format

Follow this format precisely.

```text
Readiness:
- implement | handoff-or-commit | revise | pause-lane | stop-factory | blocked

Changed slices:
- <slice id or none>

Checks run:
- <command and result>

Open gaps:
- <gap id or none>

Largest unresolved blocking probability:
- <percent or none>

Evidence summary:
- <brief evidence>

Next action:
- <exact next step>
```

## Notes

- This file intentionally removes the long historical iteration trail from the older plans.
- The strict self-QA ordering from the QA Final plan is preserved because it is the strongest part of that document.
- The concrete branch-readiness conclusion from the Opus review is preserved because it is the strongest evidence summary in the plan family.
- If the worktree moves materially after this file is written, rerun the slice-specific checks instead of copying forward the March 27, 2026 readiness conclusion.
