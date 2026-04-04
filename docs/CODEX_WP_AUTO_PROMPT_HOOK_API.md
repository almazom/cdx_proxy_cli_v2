# codex_wp Auto-Prompt Hook API

**Last verified:** 2026-04-04
**Status:** OK

## Purpose

This document explains how to run the new dynamic stop-hook prompt flow in
`bin/codex_wp`.

Use it when you want the next resume prompt to be generated from the current
session context instead of repeating one static string on every stop.

This is the operator-facing guide for:

- `--hook-prompt-mode static|auto|hybrid`
- `--hook-auto-stop-on-complete`
- dynamic next-prompt generation in headless `exec --json` loops
- notification behavior and finish reasons

## Inputs

Prepare these inputs before you start:

- a project root passed with `-C <path>` or implied by the current directory
- an initial task prompt for the first `exec --json` turn
- a hook budget via `--hook-times <n>`
- a next-prompt strategy via `--hook-prompt-mode static|auto|hybrid`
- a fallback `--hook-prompt` when using `static` or `hybrid`
- an operator delivery choice such as `telegram`, `mattermost`, or `manager`

## Mental Model

`codex_wp` can supervise a headless Codex run as a train of turns:

1. run the initial `exec --json` prompt
2. wait for the Stop event
3. decide what the next prompt should be
4. send a stop notification
5. resume the same session with that next prompt
6. repeat until the hook budget ends or the task is marked complete

The important change is step 3:

- `static`: always reuse the same `--hook-prompt`
- `auto`: ask Codex to generate the logically next prompt from session context
- `hybrid`: try auto first, then fall back to `--hook-prompt` if auto generation fails

## Pre-checks

- Auto and hybrid prompt modes are supported only for headless runs.
- Valid headless entry points are `bin/codex_wp exec --json ...` and `bin/codex_wp -p '...' ...`.
- `--hook stop` and `--hook-times <n>` are always required.
- `--hook-prompt-mode` defaults to `static`.
- Interactive `bin/codex_wp ... --hook stop ...` still uses `cdx-hook` and remains static-only.
- Zellij launch modes do not support `--hook`.
- `--hook-auto-stop-on-complete` is valid only with `--hook-prompt-mode auto` or `hybrid`.
- `--hook-supervision observation|management` is supported only for headless `exec --json` runs.

## Flag Contract

### Primary flags

- `--hook stop`
- `--hook-times <n>`
- `--hook-prompt-mode static|auto|hybrid`
- `--hook-auto-stop-on-complete`

### Prompt requirements by mode

- `static`
  - `--hook-prompt` is required
  - the same prompt is reused for every resume step
- `auto`
  - `--hook-prompt` must not be provided
  - the wrapper generates the next prompt automatically
- `hybrid`
  - `--hook-prompt` is required
  - the wrapper tries auto generation first
  - if auto generation fails, it uses the static fallback prompt

### Delivery and supervision flags

- `--hook-delivery mattermost|telegram|both|manager`
- `--hook-target <target>` for `telegram` or `both`
- `--hook-last-message-format raw|ru3`
- `--hook-supervision observation|management`
- `--hook-extract-intent`

`--hook-supervision` remains the preferred human-facing API when a parent
manager consumes JSON hook events. It resolves to manager delivery internally
and does not change the auto-prompt contract.

## How Auto Prompt Generation Works

For `auto` and `hybrid`, `codex_wp` builds a small structured generation request
after each stop.

The wrapper gathers:

- the initial prompt
- the current resume prompt
- the latest assistant message
- the current turn number
- the total hook budget
- the fallback prompt, if any
- up to the last 6 recent user/assistant messages from the session file under
  `~/.codex/sessions`

Then it runs an internal, read-only helper Codex call with an output schema.

Current internal shape:

```bash
codex exec --json --ephemeral --skip-git-repo-check \
  -C "<project-root>" \
  -s read-only \
  --dangerously-bypass-approvals-and-sandbox \
  --output-schema "<schema-path>" \
  -o "<output-path>" \
  -
```

The auto generator must return JSON matching this schema exactly:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "continue_session",
    "next_prompt",
    "operator_summary",
    "reasoning_note"
  ],
  "properties": {
    "continue_session": { "type": "boolean" },
    "next_prompt": { "type": "string" },
    "operator_summary": { "type": "string" },
    "reasoning_note": { "type": "string" }
  }
}
```

### Field meaning

- `continue_session`
  - `true`: resume the session with `next_prompt`
  - `false`: do not continue unless hybrid fallback or auto-stop rules say otherwise
- `next_prompt`
  - required when `continue_session=true`
  - must be a short actionable user prompt for the next step
- `operator_summary`
  - one concise operator-facing sentence
  - used as the finish reason when auto-stop exits early
- `reasoning_note`
  - a short internal note
  - currently normalized and validated, but not surfaced as the main operator message

## Runtime Decision Rules

After each completed turn, if more hook budget remains:

### `static`

- use `--hook-prompt`
- mark next prompt source as `static`

### `auto`

- try to generate the next prompt
- if `continue_session=true`, resume with the generated prompt
- if `continue_session=false` and `--hook-auto-stop-on-complete` is enabled:
  - stop early with a successful `complete` event
  - use `operator_summary` as the finish reason when available
- if `continue_session=false` and auto-stop is disabled:
  - fail the run
- if generation is invalid or missing:
  - fail the run

### `hybrid`

- try to generate the next prompt
- if auto generation succeeds and `continue_session=true`:
  - resume with the generated prompt
- if auto generation is invalid:
  - resume with `--hook-prompt`
- if `continue_session=false` and auto-stop is enabled:
  - stop early with success
- if `continue_session=false` and auto-stop is disabled:
  - resume with `--hook-prompt`

## Notification Contract

Stop notifications now include the resolved next prompt source.

Expected line shape:

```text
▶ next prompt (static): <prompt>
▶ next prompt (auto): <prompt>
▶ next prompt (fallback): <prompt>
```

Completion notifications include a finish reason.

Current common finish reasons:

- `hook budget exhausted`
- `Task already complete.`
- `auto prompt marked the task complete`

Failure notifications can include:

- `failed to generate the next prompt in auto mode`
- `auto prompt marked the task complete, but --hook-auto-stop-on-complete is disabled`
- `session_id changed unexpectedly`
- `failed to parse session_id from codex JSON output`
- `codex exec failed (exit N)`

When `--hook-supervision` is used, manager JSON event shape stays the same.
Auto-prompt mode changes how the next prompt is resolved, not the outer manager
event contract.

## Operator Examples

### 1. Static mode

Use this when the same resume instruction is correct for every step.

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

bin/codex_wp exec --json --skip-git-repo-check -C /tmp/demo \
  "Inspect the repository and list the first issue to fix." \
  --hook stop \
  --hook-prompt "Continue with the next concrete step." \
  --hook-times 3 \
  --hook-delivery telegram \
  --hook-target @ops
```

Behavior:

- every resume uses the same static prompt
- notifications show `▶ next prompt (static): Continue with the next concrete step.`

### 2. Auto mode with early stop on completion

Use this when the wrapper should compute the next prompt from the actual session
history and stop once the task appears done.

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

bin/codex_wp exec --json --skip-git-repo-check -C /tmp/demo \
  "Implement the requested change and stop when the repo is in a clean validated state." \
  --hook stop \
  --hook-prompt-mode auto \
  --hook-auto-stop-on-complete \
  --hook-times 5 \
  --hook-supervision observation
```

Behavior:

- `codex_wp` generates a new prompt after each stop
- notifications show `▶ next prompt (auto): ...`
- if auto generation returns `continue_session=false`, the run ends successfully
- the finish reason comes from `operator_summary` when present

### 3. Hybrid mode with fallback prompt

Use this when you want dynamic prompts, but you still want a safe default if the
auto generator fails or returns invalid JSON.

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

bin/codex_wp exec --json --skip-git-repo-check -C /tmp/demo \
  "Review the current implementation and continue until the critical path is finished." \
  --hook stop \
  --hook-prompt-mode hybrid \
  --hook-prompt "Continue with the next highest-priority unfinished step." \
  --hook-auto-stop-on-complete \
  --hook-times 5 \
  --hook-delivery telegram \
  --hook-target @ops
```

Behavior:

- successful auto generation uses `next_prompt`
- invalid auto generation falls back to the static prompt
- notifications show `▶ next prompt (fallback): ...` when fallback was used

### 4. Headless shortcut via `-p`

`-p/--prompt` is valid because it already implies `exec --json`.

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

bin/codex_wp -p "Draft the first implementation step." \
  --hook stop \
  --hook-prompt-mode auto \
  --hook-auto-stop-on-complete \
  --hook-times 4
```

## What Is Not Supported

- interactive `codex_wp --hook stop` with `--hook-prompt-mode auto`
- interactive `codex_wp --hook stop` with `--hook-prompt-mode hybrid`
- interactive `codex_wp --hook stop` with `--hook-auto-stop-on-complete`
- zellij launch modes combined with `--hook`

If you need dynamic next prompts, use a headless wrapper loop.

## Validation Checklist

Before treating an auto-prompt flow as production-ready, verify:

- the initial run is `exec --json`
- the session id stays stable across resumes
- notifications show the expected next prompt source
- early completion happens only when `--hook-auto-stop-on-complete` is intended
- hybrid fallback text is sensible enough to carry the task if auto generation fails
- the prompt budget in `--hook-times` matches the expected task depth

## Practical Recommendations

- Start with `hybrid` first if the task domain is new or unstable.
- Use `auto` only when you are comfortable failing the run on invalid generator output.
- Keep fallback prompts short and action-oriented.
- Treat `operator_summary` as the human-readable completion reason, not as a new resume prompt.
- Prefer `--hook-supervision observation|management` when another tool consumes manager JSON lines.
- Prefer `telegram` or `manager` for automation; use Mattermost formatting controls only when that channel matters.

## Notes

- The dynamic prompt engine is implemented inside `bin/codex_wp`; it does not change the legacy `cdx-hook` interactive contract.
- The helper generation step is intentionally isolated with `--ephemeral`, `-s read-only`, and `--output-schema`.
- If you want deterministic recovery behavior, `hybrid` is the safest mode because it preserves a usable fallback prompt.
