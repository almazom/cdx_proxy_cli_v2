# BLACK_WHITE

This file explains the forward-order causal flow behind the current
`codex_wp` auto-prompt hook system.

## Hook Loop

1. `bin/codex_wp` starts a headless `exec --json` run.
2. The wrapper captures the session id and the latest assistant message.
3. If hook budget remains, it decides the next prompt source:
   - `static`: reuse `--hook-prompt`
   - `auto`: generate the next prompt from session context
   - `hybrid`: try auto, then fall back to `--hook-prompt`
4. The wrapper emits a stop notification including the next prompt source.
5. The wrapper resumes the same session with `exec resume --json`.
6. The loop ends when:
   - hook budget is exhausted
   - auto mode marks the task complete and auto-stop is enabled
   - an error aborts the run

## Auto Prompt Generator

The auto generator collects:

- initial goal
- current prompt
- latest assistant message
- current turn and total budget
- fallback prompt
- recent session messages

Then it asks Codex to produce schema-validated JSON with:

- `continue_session`
- `next_prompt`
- `operator_summary`
- `reasoning_note`

## Why This Matters

Without the auto layer, stop-hook loops can only repeat one static resume
instruction. With the auto layer, the next prompt can adapt to what actually
happened in the previous turn while staying machine-checkable.
