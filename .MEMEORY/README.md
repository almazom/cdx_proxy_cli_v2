# .MEMEORY

## Purpose

`.MEMEORY/` is the repository-local knowledge system.

The name is intentionally spelled `.MEMEORY` to match the Memento-inspired
workflow: remember through fragments, snapshots, and reverse chronology.

Use this folder to keep operational knowledge compact, current, and easy to
rebuild after interruption.

## Mental Model

Organize knowledge like a Memento case board:

- `TATTOOS.md`
  - immutable or high-confidence truths
  - change rarely
- `TIMELINE.md`
  - newest-first index of meaningful changes
  - reverse chronology is the default view
- `SCENES/`
  - one file per important event, run, or feature milestone
  - preserve the local context of what changed
- `POLAROIDS/`
  - snapshots of important components, commands, or documents
  - each file answers: what this is, what we trust, what to watch
- `BLACK_WHITE.md`
  - forward-order explanation of how the system really works
  - use this for causal flow, not event history
- `OPEN_LOOPS.md`
  - unresolved questions, risks, and follow-ups

## Required Steps

When you finish meaningful work:

1. Add or update a `SCENES/` note for the event.
2. If the result changed a stable fact, update `TATTOOS.md`.
3. If the result changed understanding of a component, update a `POLAROIDS/` snapshot.
4. Add the new scene to the top of `TIMELINE.md`.
5. Move unresolved items into `OPEN_LOOPS.md` instead of hiding them in prose.

## Entry Rules

### Scene naming

Use this filename pattern:

```text
YYYY-MM-DD__short_slug.md
```

Example:

```text
2026-04-04__codex_wp_auto_prompt_hook_api.md
```

### Scene structure

Keep scenes short and factual. Prefer this shape:

```md
# <scene title>

## What happened
## Why it matters
## Evidence
## What is still unknown
## Next likely move
```

### Polaroid structure

Each `POLAROIDS/*.md` file should answer:

- what this artifact or component is
- what behavior is currently trusted
- what constraints matter
- what can break or drift
- where to read more

## Validation Rules

- `TATTOOS.md` must contain only high-confidence statements.
- `TIMELINE.md` must stay newest first.
- `SCENES/` should not be rewritten into clean history; keep the event boundary visible.
- `OPEN_LOOPS.md` should contain only unresolved items.
- `POLAROIDS/` should stay operational, not narrative.

## Notes

- This folder is for condensed knowledge, not for long design documents.
- Canonical detailed docs still live under `docs/`.
- `.MEMEORY/` should point to canonical docs instead of copying them.
