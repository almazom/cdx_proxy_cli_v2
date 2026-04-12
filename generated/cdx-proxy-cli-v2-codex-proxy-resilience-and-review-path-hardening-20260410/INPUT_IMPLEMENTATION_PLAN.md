# Implementation Plan: cdx_proxy_cli_v2 | Codex Proxy Resilience and Review-Path Hardening | v1

## Summary

Harden `cdx_proxy_cli_v2` against the failure pattern observed on 2026-04-10:

- `codex_wp review` can stall on `models_manager` refresh with `timeout waiting for child process to exit`
- proxy management health reads can time out instead of returning a bounded degraded snapshot
- proxy runtime logs show repeated `BrokenPipeError` around upstream result delivery
- `auto_heal.failure` can keep extending blacklist windows without enough operator-visible diagnosis
- the auth pool can become degraded rather than fully dead: some keys stay healthy, some turn `auth_failed`, and some approach quota exhaustion at the same time

The goal is not a broad refactor. The goal is to make the proxy operable under real degraded conditions, keep the management plane responsive, reduce false or sticky auth ejection, and make review-path failures diagnosable fast enough that `codex_wp review` becomes trustworthy again.

## Why Now

The proxy currently has a dangerous middle state:

- it is not fully down, so operators keep routing work through it
- it is not healthy enough to give fast trustworthy answers through `/health`, `cdx doctor`, and `codex_wp review`
- its current failure signals are fragmented across CLI output, `rr_proxy_v2.log`, `rr_proxy_v2.events.jsonl`, and Codex runtime stderr

That combination wastes time and causes false ambiguity: the operator cannot quickly tell whether the real blocker is auth exhaustion, broken management endpoints, proxy write-path instability, or the review runtime itself.

## Observed Evidence To Preserve

Record these observations directly in the backlog scope so later execution does not need chat replay:

1. A live `codex_wp review --commit b84ba3e` reproduction ended with `models_manager timeout waiting for child process to exit`, so review instability is not only a remote worker problem.
2. `cdx doctor --probe` reported a mixed pool rather than a total outage: `14 healthy`, `6 auth_failed`, and `/health` timing out.
3. `cdx all` showed some keys still green, several near empty quota, and others blacklisted or unknown. This is a degraded pool problem, not simply "no keys left".
4. `/home/pets/.codex/_auths/rr_proxy_v2.log` showed repeated `BrokenPipeError` in `_send_upstream_result`.
5. `/home/pets/.codex/_auths/rr_proxy_v2.events.jsonl` showed repeated `auto_heal.failure` events and blacklist extensions.

## Scope

### In Scope

- management-plane reliability for `/debug`, `/health`, and `/trace`
- auth rotation and auto-heal behavior under mixed healthy/degraded pools
- upstream response write-path hardening around client disconnects and partial stream delivery
- review-path diagnostics where proxy or model discovery instability blocks `codex_wp review`
- operator-facing observability and runbook updates for fast triage
- regression coverage for unit, integration, e2e, and live smoke validation

### Out Of Scope

- unrelated CLI refactors
- changing the overall product direction of `cdx`
- replacing the auth model or upstream provider strategy
- speculative feature additions not tied to the failure taxonomy above

## Target Outcomes

1. `/debug`, `/health`, and `/trace` must either return quickly with bounded degraded data or fail with a clear classified error. They must not silently hang.
2. `cdx doctor` and nearby CLI health probes must surface degraded pool state truthfully instead of collapsing into generic timeout noise.
3. Client disconnects and partial stream termination must not spam unbounded `BrokenPipeError` traces or poison auth health.
4. Auto-heal must distinguish real auth recovery failures from probe-path or management-path instability and avoid indefinite blind blacklist extension.
5. Operators must be able to answer, within one short triage pass, whether the blocker is:
   - auth exhaustion
   - invalid/expired auth
   - management plane stall
   - upstream write-path breakage
   - review/model discovery stall
6. The result must be split-ready for future implementation workers.

## Verified Repo Surfaces

### Primary Code Paths

- `src/cdx_proxy_cli_v2/proxy/server.py`
- `src/cdx_proxy_cli_v2/proxy/management.py`
- `src/cdx_proxy_cli_v2/health_snapshot.py`
- `src/cdx_proxy_cli_v2/runtime/service.py`
- `src/cdx_proxy_cli_v2/auth/rotation.py`
- `src/cdx_proxy_cli_v2/auth/models.py`
- `src/cdx_proxy_cli_v2/config/settings.py`
- `src/cdx_proxy_cli_v2/cli/shared.py`
- `src/cdx_proxy_cli_v2/cli/commands/doctor.py`
- `src/cdx_proxy_cli_v2/cli/commands/trace.py`

### Existing Verification Surfaces

- `tests/proxy/test_server.py`
- `tests/proxy/test_rules.py`
- `tests/auth/test_rotation.py`
- `tests/auth/test_auto_heal.py`
- `tests/runtime/test_service.py`
- `tests/integration/test_codex_cli_patterns.py`
- `tests/integration/test_codex_wp_green_path.py`
- `tests/e2e/test_auto_heal_e2e.py`
- `tests/taad/test_taad_management_contracts.py`

### Existing Docs To Align

- `docs/auto_heal_roadmap.md`
- `docs/operations/auto_heal_runbook.md`
- `docs/operations/codex_wp_observability_runbook.md`
- `AGENTS.md`

## Implementation Strategy

### Workstream A: Reproduce And Classify The Failures

Create one crisp, repeatable failure matrix before changing behavior:

- reproduce management-plane timeout separately from full proxy outage
- reproduce `BrokenPipeError` with client disconnect or short-read stream scenarios
- reproduce review-path stall while the proxy is degraded but still partially serving traffic
- capture which failures should count against auth state and which should not

Deliverable:

- a short evidence bundle or test matrix that maps each symptom to one code path and one expected recovery behavior

### Workstream B: Keep The Management Plane Bounded

Harden the management endpoints so they stay useful during degradation:

- audit `/health` snapshot generation so one slow auth or one slow upstream usage check cannot stall the whole response forever
- prefer bounded partial data with per-auth error fields over whole-endpoint timeout
- keep `/debug` cheap and independent from heavy refresh work
- verify `runtime/service.py` startup probes continue to prefer a fast `/debug` readiness signal
- ensure CLI helpers in `cli/shared.py` and `doctor.py` classify timeout versus degraded snapshot versus auth failure

Expected code focus:

- `src/cdx_proxy_cli_v2/health_snapshot.py`
- `src/cdx_proxy_cli_v2/proxy/management.py`
- `src/cdx_proxy_cli_v2/runtime/service.py`
- `src/cdx_proxy_cli_v2/cli/shared.py`
- `src/cdx_proxy_cli_v2/cli/commands/doctor.py`

### Workstream C: Harden Upstream Response Delivery

Treat broken client connections as a write-path condition, not as a mystery runtime failure:

- isolate response writes and flushes behind a disconnect-safe helper
- close `stream_response` and `stream_connection` cleanly on short write or disconnect
- reduce noisy `BrokenPipeError` logging to one classified event per request
- confirm broken downstream sockets do not inflate auth error accounting or hide the real upstream result

Expected code focus:

- `src/cdx_proxy_cli_v2/proxy/server.py`
- `tests/proxy/test_server.py`
- `tests/proxy/test_websocket_and_auth_errors.py`

### Workstream D: Make Auth Rotation And Auto-Heal Less Sticky

The pool is currently degraded, not uniformly dead. The policy must reflect that:

- review `mark_result`, rate-limit handling, blacklist extension, and max-ejection behavior in `auth/rotation.py`
- distinguish:
  - invalid/expired auth
  - quota exhaustion / limit cooldown
  - transient 5xx or probe timeout
  - incompatible account routing
- stop extending blacklist windows blindly when the failure came from probe-path instability
- make check timeout, recovery threshold, and ejection policy explicit and configurable where the code already hints at that design
- preserve the existing guardrail that previously hard-failed keys should not receive foreground traffic unless necessary

Expected code focus:

- `src/cdx_proxy_cli_v2/auth/rotation.py`
- `src/cdx_proxy_cli_v2/auth/models.py`
- `src/cdx_proxy_cli_v2/config/settings.py`
- `src/cdx_proxy_cli_v2/proxy/server.py`
- `tests/auth/test_rotation.py`
- `tests/auth/test_auto_heal.py`
- `tests/e2e/test_auto_heal_e2e.py`

### Workstream E: Expose Better Diagnostics For Review-Path Stalls

The proxy cannot directly fix every upstream `models_manager` problem, but it can remove ambiguity:

- capture proxy-visible latency and status around model-discovery endpoints used during review startup
- expose enough `/debug` or trace metadata to tell whether the proxy answered, timed out, retried auth, or never received the request
- ensure `cdx doctor`, `cdx trace`, and nearby commands can reveal this without digging through raw logs first
- add a clear runbook step for diagnosing `timeout waiting for child process to exit` when the proxy is only partially healthy

Expected code focus:

- `src/cdx_proxy_cli_v2/proxy/server.py`
- `src/cdx_proxy_cli_v2/observability/event_log.py`
- `src/cdx_proxy_cli_v2/observability/trace_store.py`
- `src/cdx_proxy_cli_v2/cli/commands/trace.py`
- `tests/integration/test_codex_wp_green_path.py`
- `docs/operations/codex_wp_observability_runbook.md`

### Workstream F: Operator Triage And Recovery UX

Make the next diagnosis shorter:

- define one recovery path for "management plane slow"
- define one for "pool degraded but still alive"
- define one for "review path blocked by model refresh timeout"
- update docs so the operator can gather a minimal bundle:
  - `cdx doctor --probe`
  - `cdx all`
  - `cdx trace`
  - `/debug`
  - `/health?refresh=1`
  - recent `rr_proxy_v2.log` and `rr_proxy_v2.events.jsonl`

Expected code and docs focus:

- `docs/operations/auto_heal_runbook.md`
- `docs/operations/codex_wp_observability_runbook.md`
- possibly `docs/QUICKSTART.md` or nearby operator docs if command guidance changes materially

## Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-001 | `/health`, `/debug`, and `/trace` return within a bounded budget under degraded auth conditions or emit a classified explicit error instead of hanging silently. |
| AC-002 | Client disconnects and short downstream writes no longer produce repeated unclassified `BrokenPipeError` noise in normal proxy logs. |
| AC-003 | Auto-heal and auth rotation preserve service when some keys are still healthy and avoid treating every failure as a hard blacklist extension. |
| AC-004 | Operators can distinguish auth failure, quota exhaustion, management-plane stall, and review-path stall using first-class CLI or management outputs. |
| AC-005 | Docs include a truthful recovery path for the observed 2026-04-10 degradation pattern. |
| AC-006 | The implementation passes targeted tests, required e2e gates, and a live smoke check that includes `codex_wp review`. |

## Task Breakdown Ready For Carding

### T-1 Reproduce And Capture Failure Taxonomy

- build a repro matrix for the 2026-04-10 failure set
- identify which failures should mutate auth state and which should stay observability-only
- preserve concrete evidence paths and expected signals

### T-2 Bound The Management Plane

- harden `/health` refresh and snapshot behavior
- keep `/debug` cheap
- align CLI timeout/error reporting with the new bounded management behavior

### T-3 Harden Downstream Write Path

- guard response write/flush operations
- classify disconnects cleanly
- keep stream cleanup deterministic

### T-4 Improve Auth Rotation And Auto-Heal Policy

- refine classification and recovery rules
- make configurable thresholds explicit where needed
- prevent false full-pool collapse when some serviceable keys remain

### T-5 Add Review-Path Diagnostics

- instrument the path that matters for model discovery and review startup
- show enough trace/debug state to prove where the stall happened

### T-6 Upgrade Operator Observability

- surface compact triage signals in `/debug`, `cdx trace`, and related flows
- reduce raw-log dependency for first diagnosis

### T-7 Refresh Runbooks

- encode the new recovery flow and evidence bundle collection

### T-8 Verify End To End

- run targeted pytest modules
- run `make test-e2e`
- if `bin/codex_wp` or its bootstrap path changes, also run `make test-integration-codex-wp`
- run a live smoke review through the proxy and record outcome

## Verification Plan

### Targeted Tests

- `pytest tests/auth/test_rotation.py`
- `pytest tests/auth/test_auto_heal.py`
- `pytest tests/proxy/test_server.py`
- `pytest tests/runtime/test_service.py`
- `pytest tests/integration/test_codex_cli_patterns.py`
- `pytest tests/integration/test_codex_wp_green_path.py`
- `pytest tests/e2e/test_auto_heal_e2e.py`
- `pytest tests/taad/test_taad_management_contracts.py`

### Mandatory Major-Change Gate

- `make test-e2e`

### Conditional Gate

- if `bin/codex_wp` or its proxy bootstrap path changes:
  - `make test-integration-codex-wp`

### Live Smoke

- `cdx doctor --probe`
- `cdx all`
- `cdx trace`
- `codex_wp review --commit <known-good-sha>`

Success means the live smoke either completes or fails with a now-classified actionable message, not a generic opaque hang.

## Risks

| Risk | Mitigation |
|------|------------|
| Over-correcting blacklist behavior may keep genuinely bad auth in rotation too long. | Keep invalid/expired auth handling strict and preserve reason-specific classification. |
| Tight management time budgets may hide useful detail. | Return partial data plus explicit per-auth errors instead of dropping the whole response. |
| BrokenPipe handling may accidentally mask upstream regressions. | Log one classified event with request context, then suppress only duplicate stack noise. |
| Review-path failures may partly live outside the proxy. | Instrument the proxy boundary so the operator can prove whether the request crossed it. |

## Done Criteria

- all acceptance criteria are satisfied
- the implementation is safe to split into task cards and assign to workers
- the next operator can re-enter from repo artifacts alone without replaying chat
