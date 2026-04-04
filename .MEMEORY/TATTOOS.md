# TATTOOS

These are stable truths worth trusting until disproven.

- `bin/codex_wp` is the main operator-facing wrapper for Codex work in this repository.
- `--hook-prompt-mode` supports exactly `static`, `auto`, and `hybrid`.
- The default hook prompt mode is `static`.
- `auto` and `hybrid` hook prompt modes are supported only for headless `exec --json` flows.
- `bin/codex_wp -p '...'` counts as a headless entry point because it implies `exec --json`.
- Interactive `codex_wp --hook stop` still uses `cdx-hook` and remains static-only.
- `--hook-auto-stop-on-complete` requires `--hook-prompt-mode auto` or `hybrid`.
- `--hook` is not supported with Zellij launch modes.
- Auto prompt generation uses a structured JSON schema and a read-only helper Codex call.
- The operator-facing guide for this feature lives at `docs/CODEX_WP_AUTO_PROMPT_HOOK_API.md`.
