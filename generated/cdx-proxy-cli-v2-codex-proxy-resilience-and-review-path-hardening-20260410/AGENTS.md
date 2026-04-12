# Agent Instructions

This package is meant for agent-driven implementation.

Read `AGENTS.md`, `trello-cards/KICKOFF.md`, and the current card before touching code.

## Execution SSOT

- Treat `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/kanban.json` as the only writable execution state.
- Treat `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/state.json` and `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/progress.md` as derived outputs only.
- Treat `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/INPUT_IMPLEMENTATION_PLAN.md` as the planning source for this backlog item.
- Use `/home/pets/TOOLS/cdx_proxy_cli_v2` as the repo root.

## Card Lifecycle

- `backlog`: waiting on dependencies; do not implement yet.
- `ready`: actionable next card.
- `in_progress`: active implementation and TDD.
- `simplify`: run code-simplifier on touched files.
- `commit`: create the task-scoped commit.
- `codex-review`: run post-commit review for the new commit.
- `blocked`: execution is stopped on a real blocker.
- `done`: implementation, verification, commit, and review are complete.

## Package Intent

This package exists because the proxy showed a mixed degraded state on 2026-04-10:

- management health timed out
- `codex_wp review` stalled on model refresh
- runtime logs showed `BrokenPipeError`
- `auto_heal.failure` kept extending blacklist windows

Do not "fix one symptom". Keep the package aligned to the full resilience goal.

## Entry Points

- Package root: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410`
- Kickoff guide: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/KICKOFF.md`
- First ready cards: `0001`, `0003`, `0004`
