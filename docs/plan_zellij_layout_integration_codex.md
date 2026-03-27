# Plan: Zellij Template Integration for `codex_wp` (Codex)

## Purpose

Add optional zellij tab creation to `bin/codex_wp` without changing the current non-zellij flow.

The public API should be **named templates**, not arbitrary KDL generation. A template registry is easier to test, safer to evolve, and matches the actual operator use case: "open a known tab shape and run `codex_wp` inside it."

## Inputs

- `bin/codex_wp` is currently a small Bash wrapper that:
  - normalizes `-p`
  - bootstraps proxy env via `cdx proxy --print-env-only`
  - `exec`s `codex` with `openai_base_url=...`
- Current green-path behavior is covered by [`tests/integration/test_codex_wp_green_path.py`](/home/pets/TOOLS/cdx_proxy_cli_v2/tests/integration/test_codex_wp_green_path.py).
- Local verification on 2026-03-27 shows `zellij 0.44.0` is installed.
- Local verification on 2026-03-27 shows `zellij action new-tab` already supports:
  - `--layout`
  - `--cwd`
  - `--name`
  - an initial command via `-- <COMMAND>...`
- Repository rules for this scope:
  - touching `bin/codex_wp` prefers `make test-integration-codex-wp` and `make test-e2e`
  - operator-facing CLI workflow changes should be validated before handoff

## Preconditions

- No zellij flags means current `codex_wp` behavior must remain unchanged.
- P0 scope is tab creation only. Pane-by-pane mutation is out of scope.
- P0 uses checked-in templates only. No user-supplied KDL path and no "build arbitrary layout" mode.
- If zellij is requested and unavailable, fail loudly with a clear message.
- Do not close an existing tab by name unless the user explicitly asked for replacement.

## Critical Review

### `plan_zellij_layout_integration.md`

This draft should not be used as the implementation baseline.

- Rewriting `codex_wp` in Python is unnecessary regression risk.
- `--zellij-new-pane`, `--zellij-pane-count`, and `--zellij-main-size` are speculative and underspecified.
- A separate renderer layer for a few layout files is architecture-first, not use-case-first.
- It treats KDL generation itself as the feature, but the feature is really "open a known review layout."

### `plan_zellij_layout_integration_opus.md`

This draft is closer, but still not the right endpoint.

- Keeping `codex_wp` in Bash is the correct call.
- Cutting pane-count and pane-level APIs is also correct.
- The remaining weak point is that it still centers the design on rendering KDL with substitutions.
- That is unnecessary because zellij already accepts `--layout`, `--cwd`, `--name`, and an initial command.
- Default close-before-create by tab name is too destructive for an operator tool. Name collisions should fail or require an explicit replace flag.
- `--zellij-send-command` is probably not P0. First verify whether `new-tab -- <COMMAND>...` lands in the intended primary pane. If it does, there is no need for delayed command injection.

## Proposed Public API

Keep zellij mode explicit and small:

| Flag | Scope | Notes |
|------|-------|-------|
| `--zellij-new-tab <name>` | P0 | Enables zellij mode and names the new tab |
| `--zellij-template <key>` | P0 | Template key, default `three-vertical` |
| `--zellij-cwd <path>` | P0 | Explicit tab cwd; otherwise derive from inner `-C <path>` when present, else use current working directory |
| `--zellij-dry-run` | P0 | Prints resolved template path and zellij command, then exits |
| `--zellij-replace-existing` | P1 | Explicitly replace a tab with the same name if needed |

Remove from the public plan:

- `--zellij-layout`
- `--zellij-new-pane`
- `--zellij-pane-count`
- `--zellij-main-size`
- any "custom KDL" or "render arbitrary layout" option

## Template Strategy

### Public model

Treat template keys as the stable API.

Examples for P0:

- `single`
- `three-vertical`
- `three-horizontal`

Possible later additions, only when there is a concrete consumer:

- `main-left-stack`
- `main-top-stack`
- `review-compare`

### Storage model

Use checked-in static files. The filename stem is the API key.

Suggested location:

```text
layouts/zellij/
  single.kdl
  three-vertical.kdl
  three-horizontal.kdl
```

Why this is better than rendering KDL:

- adding a template is "add one file + one test", not "invent more flag semantics"
- `bin/codex_wp` can resolve the layout directly from the repo root
- `zellij action new-tab` already handles tab name and cwd, so those values do not need template substitution
- static templates make review diffs much easier to inspect

## Architecture

### Preferred P0 design

Keep the implementation mostly in `bin/codex_wp`.

Flow:

1. `codex_wp` parses and strips `--zellij-*` flags.
2. If no zellij flag is present, it follows the current path unchanged.
3. If zellij mode is requested, it:
   - resolves the template file from `layouts/zellij/<template>.kdl`
   - validates that `zellij` exists
   - validates that an active zellij session is available
   - validates that the template file exists
   - derives tab cwd from `--zellij-cwd`, else inner `-C <path>`, else `$PWD`
   - builds the inner command as a recursive `codex_wp` call without zellij flags
   - runs `zellij action new-tab --name <tab> --cwd <cwd> --layout <file> -- <inner-command...>`

This keeps shell-native proxy bootstrap semantics where they already live and avoids inflating `src/cdx_proxy_cli_v2/cli/main.py` for a wrapper-specific feature.

### Why not add a Python helper first

Do not add `cdx zellij-launch` in P0 unless Bash proves insufficient.

A helper becomes justified only if at least one of these becomes true:

- template discovery needs machine-readable output for another tool
- collision handling becomes complex
- zellij session probing needs richer logic than one shell command
- command construction becomes too brittle to test in shell

Until then, a Python helper is extra moving parts.

## Required Steps

### 1. Lock the initial template set

Ship only the templates that already have a real use case:

- `single`
- `three-vertical`
- `three-horizontal`

Do not add asymmetric "main pane" templates in the first cut unless a concrete caller already needs them.

### 2. Add static template files

Create:

- `layouts/zellij/single.kdl`
- `layouts/zellij/three-vertical.kdl`
- `layouts/zellij/three-horizontal.kdl`

Rules:

- keep them static
- avoid embedded cwd/tab-name variables
- keep pane structure obvious from the file itself

### 3. Extend `bin/codex_wp`

Add a small zellij preprocessing block that:

- extracts `--zellij-new-tab`
- extracts `--zellij-template`
- extracts `--zellij-cwd`
- extracts `--zellij-dry-run`
- leaves all non-zellij args untouched

Behavior:

- missing required tab name in zellij mode -> exit 2 with a clear message
- unknown template -> exit 2 with a clear message listing valid template keys
- missing `zellij` binary -> exit 127 with a clear message
- no active zellij session -> exit 1 with a clear message
- `--zellij-dry-run` -> print the resolved layout file and the exact `zellij action new-tab ...` command

### 4. Decide command start behavior with proof, not assumption

Primary assumption for P0:

- `zellij action new-tab -- <COMMAND>...` starts the command in the intended primary pane of the template

This must be validated manually in a live zellij session.

If that assumption fails, the fallback path is:

- keep templates
- add a minimal targeted command-injection step after tab creation
- do not broaden that fallback into a general pane-control API

### 5. Keep collision behavior safe

Default behavior for duplicate tab names:

- fail with a clear message

Do not silently close or replace an existing tab in P0.

Detection should use `zellij action list-tabs --json`, not brittle text parsing.

If automation later needs replacement, add:

- `--zellij-replace-existing`

That should be explicit.

### 6. Integrate with downstream callers via template keys

`codex-review-v2` and similar tooling should call the wrapper with a stable template key, not a raw layout path.

Example:

```bash
codex_wp \
  --zellij-new-tab "review-123" \
  --zellij-template three-horizontal \
  -C /repo review --uncommitted -
```

The contract for downstream callers is the template key list, not KDL syntax.

## Validation

### Automated

Add or update tests for:

- no-zellij path remains unchanged
- zellij flags are stripped before the inner recursive `codex_wp` call
- template key resolves to the expected `.kdl` file
- tab cwd resolution prefers explicit `--zellij-cwd`, then inner `-C`, then `$PWD`
- unknown template fails clearly
- missing active zellij session fails clearly
- dry-run prints the exact planned zellij command
- fake `zellij` invocation receives `action new-tab`, `--name`, `--cwd`, `--layout`, and the inner command

Required repo validation before handoff:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
make test-integration-codex-wp
make test-e2e
```

### Manual

Run inside a real zellij session and verify:

1. `single` opens one pane and starts the inner command correctly.
2. `three-vertical` opens three stacked panes.
3. `three-horizontal` opens three side-by-side panes.
4. The initial command lands in the intended pane.
5. Duplicate tab names fail clearly.
6. `--zellij-dry-run` performs no side effects.

## Notes

- The right abstraction is "template registry", not "layout rendering engine".
- Template growth should happen by adding new checked-in files, not by adding more shape-tuning flags.
- If future callers need template discovery, add a small machine-readable listing command later. Do not block P0 on that.
- `plan_zellij_layout_integration_opus.md` is a useful intermediate draft, but this `_codex` version is the stricter implementation target.
