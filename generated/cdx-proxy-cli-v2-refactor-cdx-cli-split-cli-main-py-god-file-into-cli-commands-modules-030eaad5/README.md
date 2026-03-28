# Implementation Plan: cdx_proxy_cli_v2 | Refactor cdx CLI: split cli/main.py God file into cli/commands/ modules, extract a declarative settings resolver to reduce build_settings() boilerplate from 200 lines to ~30, unify --force/--replace flags into consistent naming across proxy and trace subcommands, and add usage example epilogs to all subcommands. Keep full backward compatibility | v2

- Package path: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5`
- Repo root: `/home/pets/TOOLS/plan_skill_cli_v2`
- Runtime config: `/home/pets/TOOLS/split_to_tasks_skill_cli/config/runtime.yaml`
- Input plan: `INPUT_IMPLEMENTATION_PLAN.md`
- Cards: `4`
- Total story points: `8`
- First card: `0001`
- Execution SSOT: `trello-cards/kanban.json`
- Derived state: `trello-cards/state.json`
- Progress view: `trello-cards/progress.md`
- Board view: `trello-cards/BOARD.md`
- Kickoff guide: `trello-cards/KICKOFF.md`
- Capability progress: `capability_progress.json`
- Cards catalog: `cards_catalog.md`
- Quality gate: `trello_quality_gate.json`
- Expert gate: `satisfaction 98, confidence 95, developer success 98, blockers none`
- Agent instructions: `AGENTS.md`

Use `trello-cards/KICKOFF.md` as the execution entry point.
