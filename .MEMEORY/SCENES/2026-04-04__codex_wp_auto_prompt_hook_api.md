# codex_wp Auto-Prompt Hook API

## What happened

The repository gained a documented dynamic stop-hook prompt flow for
`bin/codex_wp`.

The key operator-visible behaviors are:

- `--hook-prompt-mode static|auto|hybrid`
- `--hook-auto-stop-on-complete`
- notification lines that show the next prompt source
- finish reasons for successful early stop or budget exhaustion

## Why it matters

This changes the stop-hook loop from a static replay mechanism into a controlled
resume strategy.

The wrapper can now:

- continue with a context-aware next step
- stop early when the task looks done
- keep a safe fallback path through `hybrid`

## Evidence

- Canonical guide: `docs/CODEX_WP_AUTO_PROMPT_HOOK_API.md`
- Supervision contract: `docs/CODEX_WP_SUPERVISION.md`
- Runtime implementation: `bin/codex_wp`
- Green-path integration coverage: `tests/integration/test_codex_wp_green_path.py`

## What is still unknown

- Whether interactive stop-hook mode should ever support dynamic prompts
- Whether downstream manager consumers need richer auto-prompt metadata

## Next likely move

- Use `hybrid` as the default operational mode for early real-world adoption.
- Keep `auto` for flows where hard failure on invalid generation is acceptable.
