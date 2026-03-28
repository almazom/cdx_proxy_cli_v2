# Agent Instructions

This package is meant for agent-driven implementation.

Read `AGENTS.md`, `trello-cards/KICKOFF.md`, and the current card before touching code.

## Execution SSOT

- Treat `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/kanban.json` as the only writable execution state.
- Treat `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/state.json` and `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/progress.md` as derived outputs only.
- Never move cards by editing Markdown manually; use `implementation-start` and `implementation-stage` so the SSOT, state view, and progress view stay synchronized.
- Use `/home/pets/TOOLS/plan_skill_cli_v2` as the default implementation repo root for this package.
- Expert gate baseline: `satisfaction 98, confidence 95, developer success 98, blockers none`.

## Card Lifecycle

- `backlog`: waiting on dependencies; do not implement yet.
- `ready`: actionable next card.
- `in_progress`: active implementation and TDD.
- `simplify`: run code-simplifier on the touched files and keep behavior unchanged.
- `blocked`: work cannot continue; record the blocker note and evidence.
- `commit`: create the task-scoped Git commit for the current card work.
- `codex-review`: run post-commit review for the new commit and record follow-up if issues are found.
- `done`: implementation, commit, and post-commit review are complete.

Keep `blocked` because real execution needs an explicit failure lane. The old `review` state is replaced by `codex-review` after `commit`.

## Required Workflow

1. Start one `ready` card with `implementation-start`.
2. Implement the card using the card file as the source of truth for files, tasks, verification, and acceptance criteria.
3. When implementation and TDD are done, move the card to `simplify` with `implementation-stage`.
4. Run code-simplifier and re-check the verification steps before moving the card to `commit`.
5. Create the task-scoped commit and then move the card to `codex-review` with `implementation-stage`.
6. Run codex-review against that commit and only then move the card to `done` with `implementation-stage`.
7. If the card is stuck, move it to `blocked` with a real note instead of silently switching tasks.

## Commands

Start implementation:
```bash
PYTHONPATH=src python -m split_to_tasks_skill_cli implementation-start --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5 --repo-root /home/pets/TOOLS/plan_skill_cli_v2
```

Move a card into simplify:
```bash
PYTHONPATH=src python -m split_to_tasks_skill_cli implementation-stage --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5 --card 0001 --to simplify --note "Implementation complete; run code-simplifier"
```

Move a card into commit:
```bash
PYTHONPATH=src python -m split_to_tasks_skill_cli implementation-stage --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5 --card 0001 --to commit --note "Simplification and verification complete"
```

Move a card into codex-review:
```bash
PYTHONPATH=src python -m split_to_tasks_skill_cli implementation-stage --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5 --card 0001 --to codex-review --note "Commit created; run codex-review on the new SHA"
```

Mark a card done:
```bash
PYTHONPATH=src python -m split_to_tasks_skill_cli implementation-stage --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5 --card 0001 --to done --note "Codex review complete"
```

Show current summary:
```bash
python -m split_to_tasks_skill_cli summary --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5
```

Show the live terminal board:
```bash
python -m split_to_tasks_skill_cli board --package /home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5
```

Codex review command shape:
```bash
/home/pets/TOOLS/codex-review-skill_cli/codex-review --target /home/pets/TOOLS/plan_skill_cli_v2 --commit <sha>
```

## Entry Points

- Package root: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5`
- Kickoff guide: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/KICKOFF.md`
- Current first card: `0001`
- Execution SSOT: `/home/pets/TOOLS/cdx_proxy_cli_v2/generated/cdx-proxy-cli-v2-refactor-cdx-cli-split-cli-main-py-god-file-into-cli-commands-modules-030eaad5/trello-cards/kanban.json`
