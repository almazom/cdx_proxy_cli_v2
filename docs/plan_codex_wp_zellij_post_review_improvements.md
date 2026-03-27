# Plan: codex_wp Zellij Post-Review Improvements

## Context

This plan covers the next improvement pass after the recent `codex_wp` work on:

- floating Zellij panes
- two-pane floating pair mode
- pinned-by-default behavior
- semantic pane titles

It also includes the review workflow problems discovered while trying to run `codex_wp review` inside a floating pane.

## What Was Verified

### Floating review attempt

A live floating review pane was launched successfully, but the review command path exposed two issues:

1. `codex review --uncommitted "PROMPT"` fails with:

   `error: the argument '--uncommitted' cannot be used with '[PROMPT]'`

2. The same failure happens for:

   - `codex review --uncommitted -`
   - `codex review --base main "PROMPT"`
   - `codex review --commit HEAD "PROMPT"`

This means the current `codex review --help` contract is misleading: it advertises `[PROMPT]`, but in practice prompt + source-selector flags do not work together.

### Ownership of the bug

- This is not caused by `bin/codex_wp`.
- The same behavior reproduces on the raw `codex` binary.
- However, `codex_wp` should still protect the operator from this confusing upstream failure.

## Goals

1. Make floating review workflows predictable.
2. Add clear wrapper-side guardrails around unsupported `codex review` combinations.
3. Make floating review output capturable without manual pane inspection.
4. Reduce maintenance risk in the large Zellij launch path.
5. Keep the operator-facing API explicit and honest.

## Improvement Plan

## 1. Guard `review` Argument Combinations

### Problem

The wrapper currently forwards `review` args directly. When the operator combines:

- `review --uncommitted <prompt>`
- `review --base <branch> <prompt>`
- `review --commit <sha> <prompt>`

the upstream CLI fails with a parser error that looks like a local wrapper problem.

### Change

Add a thin preflight validator in `bin/codex_wp` for `review` mode:

- detect `review` before passthrough
- detect when a positional prompt is combined with:
  - `--uncommitted`
  - `--base`
  - `--commit`
- fail early with a wrapper message that explains:
  - the limitation is upstream
  - which combinations are currently supported
  - the safe fallback command

### Proposed user-facing message

Example:

```text
codex_wp: upstream codex review currently rejects PROMPT together with --uncommitted, --base, or --commit.
Use one of:
  codex_wp review --uncommitted
  codex_wp review --base <branch>
  codex_wp review --commit <sha>
```

### Why this matters

- removes ambiguity
- prevents confusing floating-pane failures
- makes the wrapper feel reliable even when upstream is inconsistent

## 2. Add Floating Output Capture

### Problem

Today a floating pane is useful visually, but its output is not automatically persisted. That makes review and audit workflows weak:

- findings stay inside the pane
- the operator must manually copy text
- follow-up automation cannot consume the result

### Change

Add a simple output capture option for Zellij-launched commands.

Recommended shape:

- `--zellij-output-file <path>`

Behavior:

- when used with floating mode, tee pane output into a file
- preserve normal terminal output inside the pane
- write the final artifact path to stdout in dry-run / JSON result where relevant

### Minimum supported cases

- single floating pane
- floating pair pane A / pane B with separate file targets or deterministic suffixes
- review workflows

### Why this matters

- makes floating review actionable
- enables later automation
- gives a durable artifact for plans, summaries, and audits

## 3. Extract Zellij Planning Logic Out of Bash

### Problem

`bin/codex_wp` now contains a large amount of embedded logic:

- geometry parsing
- title extraction
- pair prompt resolution
- result rendering
- floating command assembly

This is workable now, but it is getting too big for safe iteration.

### Change

Move the non-shell logic into a Python module under `src/cdx_proxy_cli_v2/`.

Recommended extracted responsibilities:

- geometry parsing and validation
- semantic title extraction
- pair launch planning
- dry-run rendering payload construction

Keep shell-only concerns in `bin/codex_wp`:

- arg passthrough
- process launching
- direct `zellij` invocation

### Why this matters

- easier unit testing
- clearer separation of concerns
- less risk when changing geometry or title rules

## 4. Add Explicit Pin Control

### Problem

Pinned-by-default is correct for the current workflow, but there is no explicit CLI override.

### Change

Add explicit flags:

- `--zellij-pinned`
- `--zellij-unpinned`

Rules:

- CLI flag overrides config default
- works for single floating mode and pair mode
- dry-run must show the resolved behavior

### Why this matters

- makes the API complete
- avoids hidden env-only behavior
- keeps defaults while still allowing exceptions

## 5. Document Theme Scope Correctly

### Problem

Theme requests are easy to misunderstand as per-pane styling requests, but Zellij themes are session/UI-wide.

### Change

Add a short docs section explaining:

- theme is session-wide
- frame colors come from theme components such as:
  - `frame_selected`
  - `frame_unselected`
  - `frame_highlight`
- `codex_wp` floating panes do not have independent per-pane themes

Optional later addition:

- config/env support for a session-wide Zellij theme name

### Why this matters

- prevents wrong API expectations
- avoids adding misleading flags

## 6. Tighten Tests Around Review and Floating UX

### Add tests for

- wrapper preflight rejection of unsupported `review` argument combinations
- friendly error message text
- `--zellij-output-file` dry-run rendering
- captured output path propagation in JSON / text results
- explicit pin override flags
- config default + CLI override precedence

### Keep existing guarantees

- pinned remains default
- pair mode preserves semantic titles
- create-then-rename behavior stays intact

## Suggested Order

1. Add review preflight guardrails.
2. Add floating output capture.
3. Add explicit pin override flags.
4. Extract planning logic from bash into Python.
5. Add docs for theme scope and review limitations.

## Out of Scope

- fixing the upstream `codex review` parser/help mismatch itself
- true per-pane theme support in Zellij
- changing the default pinned behavior
- changing the default “do not close floating pane” behavior

## Definition Of Done

- confusing `review` + prompt combinations fail early with a wrapper message
- floating review output can be saved to a file without manual copy-paste
- pin behavior can be overridden explicitly from CLI
- the largest non-shell Zellij planning logic is extracted into testable Python code
- docs explain theme limitations clearly
- focused integration tests cover the new review and capture behavior
