# KICKOFF

Input plan: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/INPUT_IMPLEMENTATION_PLAN.md`
Execution SSOT: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/kanban.json`
Derived state: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/state.json`
Board: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/BOARD.md`
Progress: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/progress.md`
Cards catalog: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/cards_catalog.md`
Quality gate: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello_quality_gate.json`
Agent instructions: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/AGENTS.md`
Repo root: `/home/pets/TOOLS/plan_skill_cli_v2`
Expert gate: `satisfaction 98, confidence 95, developer success 98, blockers none`

Start sequence:
1. Read `AGENTS.md`.
2. Read `BOARD.md` and card `0001`.
3. Treat `kanban.json` as the only writable execution state.
4. Start or resume the implementation run with `implementation-start`.
5. Advance the card with `implementation-stage` through `simplify`, `commit`, `codex-review`, and `done`.
6. Let the next dependency unlock automatically after the current card is complete.

Recommended first command:
```bash
PYTHONPATH=src python -m split_to_tasks_skill_cli implementation-start --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5 --repo-root /home/pets/TOOLS/plan_skill_cli_v2
```

Plan summary: Deliver a decision-complete implementation plan for: Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility.
