# Implementation Plan: cdx_proxy_cli_v2 | Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility | v2

## Summary
Deliver a decision-complete implementation plan for: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility.
The artifact remains self-contained so another engineer or agent can execute it without relying on chat history.
**Scope:** In-scope: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility. | Out-of-scope: unrelated refactors, extra documentation, and deployment work not explicitly required by the request.

## Objective
- Deliver a decision-complete implementation plan for `cdx_proxy_cli_v2` covering: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility.
- Preserve one canonical `IMPLEMENTATION_PLAN.md` handoff artifact.
- Keep the plan specific enough for split-to-tasks to derive execution cards without extra chat context.

## Scope
- In scope: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility.
- Out of scope: unrelated refactors, speculative extra docs, and deployment work not explicitly required by the request.

## Non-Negotiable Rules
- Anchor implementation to verified repo paths only.
- Preserve `IMPLEMENTATION_PLAN.md` as the only public planning artifact.
- Allow newly discovered files only when they are verified in the repo and directly required by the same goal.
- Keep later review stages plan-only; they may enrich the plan, but they must not perform implementation edits.

## Verified Context
- Target repo: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- Top-level entries discovered during bootstrap: `.coverage`, `.flow_run_001`, `.git`, `.github`, `.gitignore`, `.mypy_cache`, `.pi`, `.pytest_cache`, `.ruff_cache`, `.venv`, `AGENTS.md`, `Makefile`, `README.md`, `SSOT_KANBAN.yaml`, `bin`, `cdx_documentation.html`, `docs`, `layouts`, `proxy_debug_report.html`, `pyproject.toml`
- Key planning anchors: `AGENTS.md`, `README.md`, `pyproject.toml`, `src`, `tests`, `docs`
- Main implementation target candidate: `src/cdx_proxy_cli_v2/cli/main.py`
- Supporting surface candidate: `src/cdx_proxy_cli_v2/config/settings.py`
- Verification surface candidate: `src/cdx_proxy_cli_v2/cli/main.py`
- Git status at bootstrap: `clean`
- Requested thoroughness: `medium`
- Caller constraints: `None provided`
- Goal-specific file matches:
- `src/cdx_proxy_cli_v2/cli/main.py` (implementation, score=72) matched `all`, `build_settings`, `cdx`, `cli`, `extract`, `file`, `force`, `from`, `full`, `main`, `main.py`, `proxy`, `py`, `settings`, `trace`
- `src/cdx_proxy_cli_v2/config/settings.py` (implementation, score=50) matched `all`, `cdx`, `cli`, `file`, `from`, `main`, `proxy`, `py`, `replace`, `settings`, `split`, `trace`
- `src/cdx_proxy_cli_v2/proxy/management.py` (implementation, score=48) matched `200`, `all`, `cdx`, `cli`, `extract`, `file`, `from`, `full`, `proxy`, `py`, `replace`, `split`, `trace`
- `src/cdx_proxy_cli_v2/observability/all_dashboard.py` (implementation, score=46) matched `200`, `30`, `all`, `cdx`, `cli`, `file`, `from`, `proxy`, `py`, `replace`
- `src/cdx_proxy_cli_v2/proxy/server.py` (implementation, score=46) matched `all`, `build_settings`, `cdx`, `cli`, `extract`, `from`, `full`, `proxy`, `py`, `settings`, `split`, `trace`

## Acceptance Criteria
| ID | Criterion | Source |
|----|-----------|--------|
| AC-001 | `src/cdx_proxy_cli_v2/cli/main.py` is updated to implement: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility. | User request |
| AC-002 | Existing behavior outside the requested change remains intact after the update. | User request |
| AC-003 | `src/cdx_proxy_cli_v2/cli/main.py` verifies the requested behavior and any preserved regression path. | Execution-readiness bar |
| AC-004 | The final handoff remains one canonical `IMPLEMENTATION_PLAN.md`. | Runtime contract |

## Architecture Fit
- `src/cdx_proxy_cli_v2/cli/main.py` - main implementation target for: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility.
- `src/cdx_proxy_cli_v2/config/settings.py` - supporting contract or interface surface that may need alignment.

## Phase 1: Implementation
Implement the requested change in the verified primary target and any required supporting surface.

**Files**
- `src/cdx_proxy_cli_v2/cli/main.py`

**Work**
- Update `src/cdx_proxy_cli_v2/cli/main.py` to implement: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility.
- Update `src/cdx_proxy_cli_v2/config/settings.py` only if the requested behavior changes its public interface or documented contract.

**Acceptance**
- `src/cdx_proxy_cli_v2/cli/main.py` is updated to implement: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility.
- Existing behavior outside the requested change remains intact after the update.

## Phase 2: Verification
Prove the requested behavior works and the plan remains ready for split-to-tasks handoff.

**Files**
- `src/cdx_proxy_cli_v2/cli/main.py`

**Work**
- Run the repo verification commands and confirm the requested behavior works without regressions.
- Confirm the exported handoff still uses one canonical `IMPLEMENTATION_PLAN.md`.

**Acceptance**
- `src/cdx_proxy_cli_v2/cli/main.py` verifies the requested behavior and any preserved regression path.
- The final handoff remains one canonical `IMPLEMENTATION_PLAN.md`.

## Tasks
### Implementation Track
- [ ] **T-1.1**: Update `src/cdx_proxy_cli_v2/cli/main.py` to implement: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility. *(AC-001, AC-002)*
- [ ] **T-1.2**: Update `src/cdx_proxy_cli_v2/config/settings.py` only if the requested behavior changes its public interface or documented contract. *(AC-001, AC-002)*

### Verification Track
- [ ] **T-2.1**: Run the repo verification commands and confirm the requested behavior works without regressions. *(AC-003)*
- [ ] **T-2.2**: Confirm the exported handoff still uses one canonical `IMPLEMENTATION_PLAN.md`. *(AC-004)*

## Risks & Constraints
| Risk | Mitigation |
|------|------------|
| Automated discovery may miss one supporting file even when the main target is correct. | Expand discovery only if implementation work reveals another verified file that is directly required by the same goal. |
| Request wording may hide product decisions not inferable from source. | Resolve with exploration first, then record only unresolved intent as explicit gaps. |

## Verification Steps
1. Run `make test` from `/home/pets/TOOLS/cdx_proxy_cli_v2` and confirm it succeeds.
2. Run `pytest -q` from `/home/pets/TOOLS/cdx_proxy_cli_v2` and confirm it succeeds.
3. Confirm the final plan still points to `IMPLEMENTATION_PLAN.md` as the only public handoff file.

## Assumptions
- The implementation will preserve `IMPLEMENTATION_PLAN.md` as the only public artifact.
- Newly discovered files may be added only when they are verified in the repo and required by the same goal.
- Review and quality stages will enrich the same canonical plan instead of creating a second public artifact.

## Assumptions & Defaults
- The implementation will preserve `IMPLEMENTATION_PLAN.md` as the only public artifact.
- Newly discovered files may be added only when they are verified in the repo and required by the same goal.
- Review and quality stages will enrich the same canonical plan instead of creating a second public artifact.
- Layer 3 will remain plan-only and will not perform fresh repo discovery.

## Done Criteria
- `src/cdx_proxy_cli_v2/cli/main.py` verifies the requested behavior and any preserved regression path.
- The final handoff remains one canonical `IMPLEMENTATION_PLAN.md`.
- The exported plan remains loadable by split-to-tasks as `IMPLEMENTATION_PLAN.md`.

## Gaps
- [x] GAP-001 | Severity: Low | Evidence: Required sections, task traceability, and architecture anchors are present. | Resolution: No plan changes required beyond summary refresh. | Plan sections updated: none

## Self-QA Summary
Status: pass
Iterations: 1/4
Open High/Critical Gaps: 0
Closed Gaps: 1

## Reviewer Coverage
- `kimi` | Status: `skipped` | Model: `kimi-k2.5` | Coverage: `missing`
- `minimax` | Status: `skipped` | Model: `minimax/MiniMax-M2.7` | Coverage: `missing`
- `copilot-opus` | Status: `skipped` | Model: `claude-opus-4.6` | Coverage: `missing`
- `codex` | Status: `timeout` | Model: `default` | Coverage: `partial`
- `glm-5-turbo` | Status: `timeout` | Model: `zai/glm-5-turbo` | Coverage: `partial`

## Review Synthesis Summary
Status: degraded
Successful reviewers: 0
Accepted findings: 0
Rejected findings: 0
Reason: No reviewer produced a usable result; synthesis carried forward self-QA feedback and current plan state.

## Quality Loop Summary
Status: pass
Iterations: 1/4
Confidence: 95% | Satisfaction: 96%

### Findings Ledger
- [ ] QL-001 | Severity: Medium | Category: review | Plan anchor: Reviewer Coverage | Failure: Parallel review did not yield structured findings, so synthesis carried forward self-QA feedback only. | Consequence: The plan is still executable, but reviewer confidence is lower than on a fully covered run. | Fix: Rerun reviewers later if stronger external review coverage is required. | Status: Open
- [x] QL-001 | Severity: Low | Category: readiness | Plan anchor: whole-plan | Failure: No executor blocker remained after automated quality checks. | Consequence: The plan can be executed without extra design decisions. | Fix: No change required. | Status: Resolved
