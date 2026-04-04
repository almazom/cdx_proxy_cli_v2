# POLAROID: bin/codex_wp

## Identity

`bin/codex_wp` is the operator wrapper around Codex that also bootstraps proxy
configuration and adds repository-specific workflow flags.

## Trusted Behaviors

- It can launch plain Codex runs.
- It can run headless `exec --json` flows.
- It owns stop-hook wrapper behavior for headless resume loops.
- It validates hook flag combinations before runtime.
- It can emit operator notifications through Mattermost, Telegram, both, or manager JSON events.

## Constraints

- Dynamic prompt modes are headless-only.
- Zellij launch modes cannot be combined with `--hook`.
- Interactive stop-hook lifecycle is still delegated to `cdx-hook`.

## Watch List

- CLI help text must stay aligned with actual validation behavior.
- Hook notification wording is part of the operator contract and should not drift casually.
- Manager-mode consumers may eventually depend on richer auto-prompt metadata.

## Read More

- `docs/CODEX_WP_AUTO_PROMPT_HOOK_API.md`
- `docs/CODEX_WP_SUPERVISION.md`
- `docs/HEADLESS_HOOK_ARITHMETIC_TRAIN_REPRO_RU.md`
