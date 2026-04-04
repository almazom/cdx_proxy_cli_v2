# POLAROID: auto_prompt_hook_api

## Identity

This is the dynamic next-prompt layer inside the `codex_wp` headless stop-hook
loop.

## Trusted Behaviors

- `static` always reuses `--hook-prompt`.
- `auto` requires schema-valid generated JSON.
- `hybrid` uses generated JSON when valid and a fallback prompt when not.
- `--hook-auto-stop-on-complete` converts `continue_session=false` into a clean early success.

## Constraints

- `auto` rejects `--hook-prompt`.
- `hybrid` requires `--hook-prompt`.
- invalid auto generation fails the run in `auto`
- invalid auto generation falls back in `hybrid`

## Watch List

- The quality of generated prompts depends on session context quality.
- If the output schema changes, docs and tests must move together.
- If finish-reason wording changes, operator notification expectations may break.

## Read More

- `docs/CODEX_WP_AUTO_PROMPT_HOOK_API.md`
- `tests/integration/test_codex_wp_green_path.py`
