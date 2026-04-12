# KICKOFF

Input plan: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/INPUT_IMPLEMENTATION_PLAN.md`
Execution SSOT: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/kanban.json`
Derived state: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/state.json`
Board: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/BOARD.md`
Progress: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello-cards/progress.md`
Cards catalog: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/cards_catalog.md`
Quality gate: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/trello_quality_gate.json`
Agent instructions: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-codex-proxy-resilience-and-review-path-hardening-20260410/AGENTS.md`
Repo root: `/home/pets/TOOLS/cdx_proxy_cli_v2`

Start sequence:
1. Read package `AGENTS.md`.
2. Read `BOARD.md` and the first ready card.
3. Treat `kanban.json` as the only writable execution state.
4. Work from the failure taxonomy before changing management-plane behavior.
5. Keep the package centered on resilience, not unrelated cleanup.

Plan summary: harden `cdx_proxy_cli_v2` against the mixed degraded-state failure observed on 2026-04-10 by bounding management endpoints, reducing write-path noise, improving auth rotation and auto-heal behavior, exposing review-path diagnostics, and proving the fixes with e2e and live smoke checks.
