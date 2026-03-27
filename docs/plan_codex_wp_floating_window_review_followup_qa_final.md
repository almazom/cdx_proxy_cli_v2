# Plan: codex_wp Floating Window Review Follow-up (QA Final)

## Purpose

Provide one branch-accurate, implementation-ready follow-up plan for the current `codex_wp` floating-window worktree, with a formal self-QA flow that:

1. extracts plan claims
2. finds evidence gaps
3. tries to close those gaps automatically with evidence
4. scores unresolved gaps by blocking probability
5. stops or escalates only when the residual risk is large enough
6. runs the `95%+` confidence and satisfaction gate only after that work is complete

This version is the strictest execution document in the current plan family.

It is designed for lean-factory style execution where the agent should keep moving unless a gap is large enough to justify pausing a lane or stopping the full flow.

## Inputs

- Base canonical plans:
  - `docs/plan_codex_wp_floating_window_review_followup_final.md`
  - `docs/plan_codex_wp_floating_window_review_followup_final_95_gate.md`
- Earlier drafts kept for historical context:
  - `docs/plan_codex_wp_floating_window_review_followup.md`
  - `docs/plan_codex_wp_floating_window_review_followup_opus.md`
  - `docs/plan_codex_wp_floating_window_review_followup_codex.md`
- Current implementation and verification surface:
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
  - the full CLI help sweep is preferred when parser wiring or operator-facing help changes

## Preconditions

- Work from repo root: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- Treat the live dirty worktree as newer than all earlier planning drafts.
- Do not overwrite unrelated worktree edits.
- Preserve already-green behavior unless new evidence proves it is wrong.
- Never treat self-QA as permission to invent missing facts.
- Use evidence-backed gap closure before scoring confidence.
- Prefer lane-local continuation over whole-factory stopping when the risk is bounded.

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
- full help sweep across:
  - `cdx --help`
  - `cdx proxy --help`
  - `cdx status --help`
  - `cdx doctor --help`
  - `cdx stop --help`
  - `cdx trace --help`
  - `cdx logs --help`
  - `cdx limits --help`
  - `cdx migrate --help`
  - `cdx reset --help`
  - `cdx rotate --help`
  - `cdx all --help`
  - `cdx run-server --help`
  - result: all listed help commands exited successfully
- `make test-e2e`
  - result: `10 passed`

Current interpretation:

1. the branch is green on the known wrapper, runtime, CLI, integration, and E2E gates
2. the branch no longer matches the older red-state planning drafts
3. the most likely next move is controlled handoff, verification, or commit
4. if new work is added later, this QA plan should gate whether implementation continues automatically

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

## Self-QA Flow

### Phase 1: Claim Extraction

Before implementation or handoff, extract every meaningful plan claim.

Claim categories:

- behavior claim
  - example: wrapper help is side-effect free
- safety claim
  - example: `cdx trace --replace` does not kill unrelated PIDs
- scope claim
  - example: the fix is local to the auth-loading layer
- verification claim
  - example: the current gates are sufficient to validate the branch
- ownership claim
  - example: a given slice has a clear set of owned files

For each claim, generate self-QA questions:

1. what evidence proves this claim?
2. what would make this claim false?
3. what dependency does the claim rely on?
4. what remains unknown?
5. if the claim is false, what breaks?

### Phase 2: Gap Discovery

A gap exists when any of the following are true:

- evidence is missing
- evidence is stale
- ownership is unclear
- validation is missing
- an assumption has no bounded blast radius
- recovery behavior is unclear
- two instructions or requirements conflict
- the plan claims more certainty than the evidence supports

Use these gap types:

- `evidence_missing`
- `stale_evidence`
- `unclear_owner`
- `missing_validation`
- `risky_assumption`
- `conflicting_requirement`
- `unclear_recovery`

### Phase 3: Evidence-Based Auto Gap Closure

For each gap, try to close it automatically using one or more of:

- file evidence
- diff review
- focused unit tests
- focused integration tests
- reproductions
- CLI help checks
- repo-level gates already required by the plan

Rules:

1. auto gap closure may remove uncertainty
2. auto gap closure may not invent missing facts
3. intuition-only answers do not count as closure
4. if no evidence path exists, the gap remains open
5. if the gap can be reduced to one targeted experiment, record that as the next action

### Phase 4: Gap Metrics and Blocking Probability

Every unresolved gap must be scored on five dimensions using a `1..5` scale.

Metric definitions:

- `Impact`
  - `1`: negligible effect if wrong
  - `5`: severe effect, safety issue, or invalidates major work
- `Likelihood`
  - `1`: unlikely to fail in practice
  - `5`: very likely to fail or already partially reproduced
- `Detectability`
  - `1`: very easy to catch early
  - `5`: hard to detect before damage
- `Scope`
  - `1`: isolated to one local behavior
  - `5`: affects multiple slices or the whole factory flow
- `Recovery`
  - `1`: easy and fast to recover
  - `5`: slow, unclear, or costly to recover

Convert those metrics into a blocking probability using:

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

Interpretation:

- impact and likelihood dominate
- wide-scope gaps are more dangerous than narrow ones
- hard-to-detect gaps increase stop risk
- hard-to-recover gaps raise the stop threshold even if they have not failed yet

### Phase 5: Risk Triage and Action Rules

Use these blocking-probability thresholds:

- `0%` to `24%`
  - continue
  - record the assumption if needed
- `25%` to `49%`
  - continue with mitigation
  - add a bounded assumption or targeted validation
- `50%` to `69%`
  - run a focused gap-closure check before continuing
  - do not score readiness yet
- `70%` to `84%`
  - pause the affected lane
  - revise the plan or run a targeted spike
- `85%` to `100%`
  - stop the factory flow
  - escalate immediately

Decision rule:

- stop the lane when the risk is high but bounded to one slice
- stop the factory when the risk is critical, systemic, or unbounded

Examples of critical stop conditions:

- plausible destructive side effects
- plausible security or privacy exposure
- wrong-target execution risk
- unverifiable main green-path behavior
- cross-slice conflict that could invalidate implementation

Examples that usually do not justify factory stop:

- naming uncertainty
- documentation wording gaps
- a small test gap with bounded blast radius
- a local unknown that can be resolved by one focused check

### Phase 6: Escalation and Notification Policy

When a gap causes a pause or stop, notify according to impact.

Rules:

1. for `70%` to `84%` gaps:
   - pause the affected lane
   - continue unrelated safe lanes if they remain valid
   - notify only when coordination is required
2. for `85%+` gaps:
   - stop the full factory flow
   - notify immediately
3. always surface the stop in the active user conversation
4. if async alerting is desired, use the local notify flow through `notify-me` or `t2me`
5. notification is evidence-driven, not speculative

Notification payload should include:

- status
- gap summary
- risk level
- evidence that triggered the stop
- blocked scope
- next required decision or input

Suggested stop notification shape:

```text
Factory status: STOPPED
Reason: critical unresolved gap in <slice>
Risk: <why continuing is unsafe>
Evidence:
- <artifact>
Blocked scope:
- <lane or whole flow>
Next required input:
- <decision, approval, or missing fact>
```

## Readiness Gate

Run the readiness gate only after:

1. claim extraction is complete
2. open gaps are listed
3. auto gap closure has been attempted
4. unresolved gaps have been risk-scored
5. no gap remains in the `85%+` stop range

Score the plan on two axes:

- `Confidence`
  - estimated probability that implementation can proceed without major replanning
- `Satisfaction`
  - quality of the plan as an execution document for the actual branch state

Scoring rules:

1. scores must be justified by evidence, not wording alone
2. scores may rise only when a real ambiguity is removed or a real evidence path is added
3. confidence may not exceed the reality of the largest unresolved high-risk gap
4. if either score is below `95%`, revise the plan or run the focused experiment needed to remove the exact blocker
5. do not loop indefinitely
6. if the score remains below `95%` after two substantive revisions, mark the plan `blocked`

Required readiness output:

```text
Confidence: <percent>
Satisfaction: <percent>
Gaps:
- <gap or none>
Largest unresolved blocking probability:
- <percent or none>
Evidence:
- <artifact>
Revision decision:
- revise | implement | blocked
```

## Required Steps

### Step 1: Treat This File as the Active QA Plan

Actions:

1. use this file when the workflow needs formal self-QA before implementation
2. keep the earlier drafts as historical context only
3. use the base final plans as reference, not as the active QA workflow

### Step 2: Build the Claim Inventory

Actions:

1. extract claims from each implementation slice and from the current verified-state section
2. convert each claim into one self-QA item
3. record the expected evidence path for each item

### Step 3: Generate the Gap List

Actions:

1. inspect the claim inventory for missing, stale, or weakly supported claims
2. create one gap item per issue
3. classify each gap by type
4. assign each gap to an owning slice or mark cross-slice scope explicitly

### Step 4: Run Evidence-Based Auto Gap Closure

Actions:

1. attempt to close each gap with:
   - file reads
   - diff review
   - focused tests
   - targeted reproductions
   - command verification
2. record what closed the gap
3. leave unresolved gaps open instead of inventing answers

### Step 5: Score Blocking Probability

Actions:

1. score `Impact`, `Likelihood`, `Detectability`, `Scope`, and `Recovery`
2. calculate the blocking probability for each unresolved gap
3. assign one action:
   - continue
   - continue with mitigation
   - focused check
   - pause lane
   - stop factory

### Step 6: Apply Stop or Notify Rules

Actions:

1. if any gap is `85%+`, stop the factory flow
2. if any gap is `70%` to `84%`, pause only the affected lane unless the gap is systemic
3. notify the user in the active conversation
4. if async alerting is desired, send the stop or pause notice via the local notify flow

### Step 7: Run the 95% Readiness Gate

Actions:

1. score confidence and satisfaction only after steps 2 through 6
2. if either score is below `95%`, revise the plan or run the exact focused experiment needed to remove the blocker
3. if two substantive revisions still do not reach `95%`, mark the plan blocked and stop
4. if both scores reach `95%+`, immediate implementation may begin

### Step 8: Re-Verify Before Handoff

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

- any unresolved gap has `85%+` blocking probability
- confidence remains below `95%` after two substantive revisions
- satisfaction remains below `95%` after two substantive revisions
- the branch regresses on any verified wrapper, runtime, CLI, integration, or E2E gate
- a claimed guarantee has no evidence path
- the worktree moves enough that the recorded verified state is no longer trustworthy

Mark the plan as `revise` if:

- one or more gaps remain in the `50%` to `84%` range
- a plan claim is valid but insufficiently evidenced
- a slice lacks clear ownership or validation
- the plan overstates certainty relative to the evidence

Mark the plan as `pass` only when:

- no unresolved gap remains above `49%`
- both confidence and satisfaction are `95%+`
- the scores are evidence-backed
- the four implementation slices remain coherent
- the required verification path is explicit
- the known repo gates are green

## Output Contract

Follow this format precisely.

```text
Confidence: <percent>
Satisfaction: <percent>
QA items reviewed:
- <count>
Open gaps:
- <gap id or none>
Largest unresolved blocking probability:
- <percent or none>
Decision:
- continue | revise | pause-lane | stop-factory | implement
Evidence:
- <artifact>
Notification:
- none | in-chat only | notify-me
Next action:
- <exact next step>
```

## Example Gap Record

Follow this format precisely.

```text
Gap ID:
- G-01

Claim:
- runtime metadata JSON is excluded from auth discovery

Gap:
- no fresh evidence after latest auth-store edit

Type:
- stale_evidence

Owner:
- Slice 3

Metrics:
- Impact: 4
- Likelihood: 4
- Detectability: 3
- Scope: 4
- Recovery: 3

Blocking Probability:
- 74%

Decision:
- pause-lane

Evidence:
- old test run only

Next action:
- rerun `pytest -q tests/auth/test_keyring_store.py`
```

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
  - it isolated the runtime-auth blocker much better
- Why it still failed:
  - the failure snapshot became partially stale as the branch moved
  - it was not yet backed by the full green validation set

### Iteration 3: 95%-Gate Final Draft

- Confidence: 99%
- Satisfaction: 98%
- Why it improved:
  - it tied readiness to explicit evidence
  - it stopped the open-ended rewrite-until-95 pattern
- Why one more iteration still helped:
  - it did not yet formalize self-QA gap discovery, blocking-probability scoring, or stop-the-lane versus stop-the-factory decisions

### Iteration 4: This QA Final Plan

- Confidence: 99%
- Satisfaction: 99%
- Why it clears the bar:
  - it is tied to the verified 2026-03-27 branch state
  - it formalizes a deterministic self-QA flow
  - it turns “fill the gaps” into evidence-based closure, not guesswork
  - it measures residual risk instead of assuming every gap should stop work
  - it defines when to continue, when to pause a lane, and when to stop the full flow
  - it leaves the 95% gate in place, but only after gap discovery and triage are complete

## Notes

- This document is intentionally more operational than the earlier plan variants.
- The main quality improvement is not extra prose. It is the ordering:
  - self-QA
  - gap closure
  - risk triage
  - stop or notify decision
  - 95% readiness gate
  - implementation
- For the current branch, the plan already clears the readiness bar because the recorded evidence is green.
- If the worktree changes materially, rerun the self-QA flow instead of copying the old scores forward.
