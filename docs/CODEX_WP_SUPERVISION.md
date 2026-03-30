# codex_wp Supervision Contract

**Last verified:** 2026-03-30
**Status:** OK

## Purpose

This document is the canonical contract for `bin/codex_wp` supervision flags in
headless hook mode.

Use this when you need one stable answer to:

- which flag is the primary human-facing API
- how phrase aliases normalize
- what manager-mode JSON events contain
- what remains headless-only today

## Recommended API

Use `--hook-supervision` as the primary human-facing API:

```bash
bin/codex_wp exec --json --skip-git-repo-check -C /tmp \
  'Reply with exactly OK and stop.' \
  --hook stop \
  --hook-prompt 'Continue.' \
  --hook-times 2 \
  --hook-supervision observation
```

Canonical supervision values:

- `observation`
- `management`

## Phrase Aliases

The wrapper accepts ergonomic phrases and normalizes them to canonical
supervision values before runtime behavior starts.

Current phrase mappings:

- `codex_wp under observation` -> `observation`
- `manage codex_wp` -> `management`
- `codex_wp under management` -> `management`

These phrases are convenience inputs. The normalized contract value is the
canonical supervision string.

## Transport Layer

`--hook-delivery` remains supported as a low-level transport override:

- `telegram`
- `manager`

Recommended rule:

- prefer `--hook-supervision` for human-facing workflows
- use `--hook-delivery` only when transport must be selected explicitly

If `--hook-supervision` is present, the wrapper resolves supervision first and
then runs manager delivery internally.

## Manager JSON Events

Manager-mode events are emitted into the existing headless `--json` stdout
stream as JSON lines.

Stable fields:

- `type`
- `delivery`
- `hook_event_name`
- `event`
- `supervision`
- `train_id`
- `session_id`
- `turn`
- `total`
- `project`
- `last_assistant_message`

Optional fields:

- `intent_text`
- `failure_text`

### Example: stop

```json
{
  "type": "hook.delivery",
  "delivery": "manager",
  "hook_event_name": "Stop",
  "event": "stop",
  "supervision": "observation",
  "train_id": "TRAIN-20260330-120000-ABCD",
  "session_id": "019d-example",
  "turn": 1,
  "total": 3,
  "project": "demo",
  "last_assistant_message": "Step 1 done"
}
```

### Example: complete

```json
{
  "type": "hook.delivery",
  "delivery": "manager",
  "hook_event_name": "Stop",
  "event": "complete",
  "supervision": "management",
  "train_id": "TRAIN-20260330-120000-ABCD",
  "session_id": "019d-example",
  "turn": 3,
  "total": 3,
  "project": "demo",
  "last_assistant_message": "All steps done"
}
```

### Example: error

```json
{
  "type": "hook.delivery",
  "delivery": "manager",
  "hook_event_name": "Stop",
  "event": "error",
  "supervision": "management",
  "train_id": "TRAIN-20260330-120000-ABCD",
  "session_id": "019d-example",
  "turn": 2,
  "total": 3,
  "project": "demo",
  "last_assistant_message": "Step 1 done",
  "failure_text": "codex exec failed"
}
```

## Headless-Only Limitation

Manager supervision is currently supported only for headless `exec --json`
runs.

Interactive hook activation still routes through `cdx-hook` and does not yet
share the same manager supervision path.

## Migration Guidance

Old style:

```bash
bin/codex_wp ... --hook-delivery manager
```

Recommended style:

```bash
bin/codex_wp ... --hook-supervision observation
```

Use `management` instead of `observation` when the parent system should treat
the run as manager-controlled rather than manager-observed, even though both
currently use the same headless manager transport.
