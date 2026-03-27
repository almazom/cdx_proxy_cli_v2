# Plan: codex_wp Floating Window Review Follow-up (QA Final — Opus Review)

## Purpose

Independent Opus 4.6 review of the QA Final plan, grounded in a fresh full-gate verification run on 2026-03-27 and a code-level audit of all four implementation slices.

This document applies the self-QA flow defined in the parent plan against live branch evidence collected by the reviewing agent, not copied from prior iterations.

## Lineage

- Parent plan: `docs/plan_codex_wp_floating_window_review_followup_qa_final.md`
- Earlier variants kept for historical context:
  - `docs/plan_codex_wp_floating_window_review_followup.md`
  - `docs/plan_codex_wp_floating_window_review_followup_opus.md`
  - `docs/plan_codex_wp_floating_window_review_followup_codex.md`
  - `docs/plan_codex_wp_floating_window_review_followup_final.md`
  - `docs/plan_codex_wp_floating_window_review_followup_final_95_gate.md`

## Fresh Verification Run

All gates re-run by Opus 4.6 on 2026-03-27:

| Gate | Command | Result |
|------|---------|--------|
| Auth keyring store | `pytest -q tests/auth/test_keyring_store.py` | 10 passed |
| Config settings | `pytest -q tests/config/test_settings.py` | 65 passed |
| Singleton | `pytest -q tests/runtime/test_singleton.py` | 5 passed |
| Service | `pytest -q tests/runtime/test_service.py` | 22 passed |
| CLI runtime flow | `pytest -q tests/integration/test_cli_runtime_flow.py` | 1 passed |
| codex_wp integration | `make test-integration-codex-wp` | 30 passed |
| E2E | `make test-e2e` | 10 passed |
| CLI help sweep | All 13 `cdx <cmd> --help` | All exited 0 |

Total: **143 tests passed, 0 failures, all 13 CLI help commands clean.**

## Self-QA: Claim Inventory

### Slice 1 — Wrapper Help and Upstream Profile Compatibility

| ID | Claim | Type | Evidence |
|----|-------|------|----------|
| C-1.1 | Help requests are side-effect free even with Zellij flags | behavior | `bin/codex_wp` lines 252–254: `is_help_request` runs before any Zellij processing; pair validation gated by `if (( ! help_requested ))` at line 258 |
| C-1.2 | Wrapper help exposes wrapper-specific options clearly | behavior | `bin/codex_wp` lines 304–336: distinct sections for General, Floating pane, Floating pair flags |
| C-1.3 | Upstream Codex help remains visible | behavior | `bin/codex_wp` lines 349–351: `exec "$codex_bin" "$@"` passes original args after wrapper help |
| C-1.4 | Upstream `-p/--profile` passes through unchanged | behavior | No matching or special handling for `-p`/`--profile` in wrapper; test at line 459 confirms |
| C-1.5 | Pair-mode validation does not run before help short-circuit | safety | Pair validation block (lines 259–276) inside `if (( ! help_requested ))` |

### Slice 2 — Safe `cdx trace --replace` PID Handling

| ID | Claim | Type | Evidence |
|----|-------|------|----------|
| C-2.1 | Live PID not terminated unless it matches expected trace process | safety | `singleton.py` lines 124–131: `process_matches` callable verified before `_terminate_pid()` |
| C-2.2 | Stale pid files cleaned up | behavior | `singleton.py` lines 138–142 (acquisition) and 149–152 (exit cleanup) |
| C-2.3 | Singleton helpers raise structured errors, not `sys.exit` | scope | `SingletonLockError` class at line 15; all error paths raise it |
| C-2.4 | CLI callers own final exit behavior | ownership | `main.py` lines 478–481: catches `SingletonLockError`, prints to stderr, returns exit code |

### Slice 3 — Runtime Auth Discovery and Keyring Behavior

| ID | Claim | Type | Evidence |
|----|-------|------|----------|
| C-3.1 | Runtime metadata JSON excluded from auth input | safety | `health_snapshot.py` line 122: `access_token` intentionally excluded |
| C-3.2 | Runtime paths avoid unnecessary keyring lookups | behavior | `store.py` lines 129–133: `should_query_keyring` gated by `prefer_keyring`; `proxy/server.py` lines 268, 443, 555, 800 all pass `prefer_keyring=False` |
| C-3.3 | Legitimate keyring-backed auth still works | behavior | `store.py` lines 134–140: keyring override path; `test_keyring_store.py` line 36 covers this |
| C-3.4 | Health/doctor/wrapper flows stay fast and deterministic | verification | All proxy internal auth uses `prefer_keyring=False`; integration tests pass without keyring backend |

### Slice 4 — Auth-Dir-Scoped Env Handling

| ID | Claim | Type | Evidence |
|----|-------|------|----------|
| C-4.1 | Inherited env from other auth dirs does not redirect runtime | safety | `settings.py` lines 413–435: explicit auth_dir scopes .env resolution; `scoped_env_file_path` (lines 106–116) returns `None` for out-of-scope paths |
| C-4.2 | Explicit env files work when intentionally provided | behavior | `settings.py` line 414: `env_file` parameter honored directly; test at line 558 |
| C-4.3 | Resolved auth dir owns its `.env` | ownership | `settings.py` lines 418–420: `env_file_path(str(auth_dir_path))` used when auth_dir is explicit; test at line 547 |
| C-4.4 | Stale `CLIPROXY_AUTH_DIR` does not survive startup | safety | `CLIPROXY_AUTH_DIR` inside `.env` never overrides `initial_auth_dir`; test at line 586 places stale value and verifies it is ignored |

## Self-QA: Gap Discovery

### Methodology

For each claim above, the reviewing agent asked:

1. What evidence proves this claim?
2. What would make this claim false?
3. What dependency does the claim rely on?
4. What remains unknown?
5. If the claim is false, what breaks?

### Discovered Gaps

After code-level inspection and full gate verification, **no open gaps were found** in any of the four slices.

All 17 claims have both direct code evidence (line-level) and passing test evidence. No claim relies on stale evidence, unresolved assumptions, or missing validation.

The following borderline items were reviewed and closed:

| Item | Concern | Closure |
|------|---------|---------|
| C-3.4 (determinism) | Indirect evidence via `prefer_keyring=False` rather than a dedicated latency test | Closed: all 4 proxy auth call sites explicitly pass the flag; integration test passes with poison env (test_cli_runtime_flow.py line 69); behavior is deterministic by construction |
| C-4.4 (stale env) | .env parsing is delegated to pydantic-settings; could a future pydantic version change precedence? | Closed: current code explicitly resolves auth_dir before env loading; test_auth_dir_scoped_env_file_does_not_redirect_auth_dir confirms the invariant; blast radius is bounded to one function |

## Self-QA: Gap Metrics

No unresolved gaps to score. All discovered items were closed with evidence during Phase 3.

## Risk Triage

No gaps remain in any blocking-probability range. The factory flow has no pending stops or lane pauses.

## Readiness Gate

```text
Confidence: 99%
Satisfaction: 99%
QA items reviewed:
- 17 claims across 4 slices
Open gaps:
- none
Largest unresolved blocking probability:
- none
Decision:
- implement
Evidence:
- 143 tests passed (10 auth + 65 config + 5 singleton + 22 service + 1 cli-flow + 30 codex-wp + 10 e2e)
- 13/13 CLI help commands clean
- all 17 claims verified at code line level
- 2 borderline items closed with evidence
Notification:
- none
Next action:
- controlled handoff or commit
```

## Confidence Loop

### Iteration 1–4: See Parent Plan

Prior iterations are documented in the parent QA Final plan. They trace the progression from 68%/66% (early red-state drafts) through 99%/99% (QA Final).

### Iteration 5: This Opus Review

- Confidence: 99%
- Satisfaction: 99%
- Why it holds:
  - independent full-gate run confirms all 143 tests green
  - code-level audit of all 17 claims found no gaps
  - two borderline items were examined and closed with evidence
  - no scores were copied from prior iterations; all are freshly derived
- Why not 100%:
  - the worktree has uncommitted changes; a future rebase or merge could introduce regressions
  - no negative-path stress testing was performed (e.g., actual keyring backend present, real Zellij session)
  - these are acceptable residual risks for a controlled handoff

## Notes

- This review was generated by Claude Opus 4.6 on 2026-03-27.
- The main contribution over the parent plan is not new process. It is fresh, independently collected evidence applied to the existing self-QA framework.
- If the worktree changes materially after this review, rerun the self-QA flow rather than copying these scores.
