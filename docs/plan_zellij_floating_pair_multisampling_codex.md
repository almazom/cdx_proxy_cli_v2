# Plan: Zellij Floating Pair Integration for `codex_wp` (Codex)

## Purpose

Add an explicit two-pane floating mode to `bin/codex_wp` for side-by-side Codex runs and multisampling.

The goal is not "arbitrary multi-pane orchestration". The goal is a narrow, operator-friendly API that can:

- open exactly two floating Codex sessions in one command
- accept a distinct prompt source for each session
- keep the current single-floating and non-zellij flows unchanged
- stay testable and shell-safe

The public API should be a dedicated pair mode, not an overloaded extension of the current single-pane flags.

## Inputs

- `bin/codex_wp` already supports:
  - the normal one-shot proxy bootstrap path
  - a single floating zellij pane
  - post-create pane rename via `zellij action rename-pane --pane-id ...`
  - semantic title extraction for a single floating pane
- Current green-path behavior is covered by [`tests/integration/test_codex_wp_green_path.py`](/home/pets/TOOLS/cdx_proxy_cli_v2/tests/integration/test_codex_wp_green_path.py).
- Current config defaults are loaded through [`src/cdx_proxy_cli_v2/config/settings.py`](/home/pets/TOOLS/cdx_proxy_cli_v2/src/cdx_proxy_cli_v2/config/settings.py).
- Local verification on 2026-03-27 shows the installed `zellij` supports:
  - `run --floating`
  - `action list-tabs --json --state --dimensions`
  - `action rename-pane --pane-id <id> <name>`
- Repository rules for this scope:
  - touching `bin/codex_wp` prefers `make test-integration-codex-wp` and `make test-e2e`
  - operator-facing CLI workflow changes should be validated before handoff

## Preconditions

- No new flags means current `codex_wp` behavior must remain unchanged.
- P0 scope is exactly two floating panes.
- P0 scope is `exec` only. It is not a general-purpose multi-command launcher.
- P0 accepts one prompt source per pane:
  - inline text
  - UTF-8 prompt file contents
- P0 uses named pair layouts, not raw per-pane coordinates from the CLI.
- P0 should avoid destructive cleanup by default. If pane A opens and pane B fails, pane A should remain unless the user explicitly asks for rollback in a later feature.
- All geometry defaults must live in config, not inline shell literals.

## Critical Review

### Why not overload the current single-floating API

A repeated-flag model such as "pass `--zellij-floating` twice with two prompts" is too ambiguous:

- it is unclear which flags belong to pane A vs pane B
- quoting becomes brittle quickly
- the parser becomes hard to reason about in Bash
- the dry-run output becomes much harder to validate

This is the wrong abstraction.

### Why not accept "one string with two commands"

A "one command string containing two window specs" approach is also the wrong abstraction:

- it turns the CLI into a mini-language
- shell quoting and escaping become the real feature
- file-based prompts and shared flags become awkward
- error messages become poor because parsing happens too late

This is not a good operator API.

### Why not support arbitrary `N` floating panes

Arbitrary `N` is possible later, but it should not be P0:

- layout complexity grows immediately
- failure handling becomes combinatorial
- observability becomes harder
- the test matrix expands sharply
- the concrete use case here is two panes for comparison, not a general layout planner

P0 should stay at exactly two panes.

### Why not build a JSON manifest first

A manifest may become useful later for richer orchestration, but it is too heavy for the first cut:

- the immediate operator need is a shell command
- the current wrapper already owns the recursive launch pattern
- a manifest is justified only after the pair API proves insufficient

## Proposed Public API

Add a dedicated pair mode:

| Flag | Scope | Notes |
|------|-------|-------|
| `--zellij-floating-pair` | P0 | Enables two-pane floating mode |
| `--pair-layout <key>` | P0 | Named pair layout, default `top-right-double` |
| `--a-prompt <text>` | P0 | Inline prompt for pane A |
| `--a-file <path>` | P0 | Prompt file for pane A; file contents become the prompt body |
| `--b-prompt <text>` | P0 | Inline prompt for pane B |
| `--b-file <path>` | P0 | Prompt file for pane B; file contents become the prompt body |
| `--a-title <text>` | P1 | Explicit title override for pane A |
| `--b-title <text>` | P1 | Explicit title override for pane B |
| `--zellij-pair-json` | P0 | Emits machine-readable launch metadata for the outer command |
| `--zellij-dry-run` | P0 | Prints both resolved launch commands and titles, then exits |
| `--zellij-cwd <path>` | P0 | Shared cwd for both panes; otherwise derive from shared inner `-C`, then `$PWD` |

Rules:

- exactly one of `--a-prompt` or `--a-file` is required
- exactly one of `--b-prompt` or `--b-file` is required
- `--zellij-floating-pair` cannot be combined with:
  - `--zellij-floating`
  - `--zellij-new-tab`
- P0 should treat remaining non-zellij args after pair parsing as shared inner `exec` flags that apply to both panes
- prompt text itself should not be passed in the shared tail; prompt ownership belongs only to `--a-*` and `--b-*`

### Argument grammar

Use an explicit shared-args boundary:

```text
bin/codex_wp \
  --zellij-floating-pair \
  <pair-flags...> \
  -- \
  <shared-inner-exec-args...>
```

Rules:

- everything before `--` must be pair-mode control flags
- everything after `--` is appended to both inner `codex_wp exec ...` commands
- if `--` is omitted, pair mode runs with no shared inner args
- bare non-flag tokens before `--` should be rejected as ambiguous

This keeps parsing deterministic and prevents prompt text from accidentally landing in the wrong scope.

### Example: two inline prompts

```bash
bin/codex_wp \
  --zellij-floating-pair \
  --pair-layout top-right-double \
  --a-prompt "Review proxy retry jitter behavior." \
  --b-prompt "Review auth cooldown behavior." \
  -- --json --ephemeral --skip-git-repo-check
```

### Example: one inline prompt and one prompt file

```bash
bin/codex_wp \
  --zellij-floating-pair \
  --pair-layout top-right-double \
  --a-prompt "Compare current implementation against failure-handling expectations." \
  --b-file prompts/failure_review.md \
  --zellij-cwd /home/pets/TOOLS/cdx_proxy_cli_v2 \
  -- --json
```

## Prompt Source Strategy

P0 should keep prompt loading simple and explicit.

### Inline prompt

`--a-prompt` and `--b-prompt` pass literal prompt text.

### Prompt file

`--a-file` and `--b-file` should:

- read the file contents as UTF-8 text
- fail before creating any panes if the file is missing or unreadable
- treat the full file contents as the prompt body
- preserve the file contents exactly rather than trimming trailing newlines

Do not reinterpret a prompt file as an attached `@path` reference in P0. The user asked for prompt files, not file-attachment indirection.

If the user wants file references inside the prompt, they can still use the existing `-f` flow through the shared inner args later.

## Pair Layout Strategy

### Public model

Use named layouts only.

P0 should ship one default layout:

- `top-right-double`

Possible later additions, only after real use:

- `right-stack-wide`
- `side-by-side-right`
- `top-band-double`

### Layout behavior for `top-right-double`

Treat the pair as one logical floating region anchored to the top-right.

That region should be split into:

- pane A on top
- pane B below
- one configurable gap between them

The key point is that the CLI should not expose raw `x/y/width/height` for each pane in P0.

### Geometry formulas for `top-right-double`

Use the same measure parsing model as the current single floating flow:

- percentages are resolved against the active viewport
- integer values are treated as absolute terminal cells

Then compute:

- `x = max(0, columns - pair_width - pair_right)`
- `y_a = max(0, pair_top)`
- `height_a = floor((pair_total_height - pair_gap) / 2)`
- `height_b = pair_total_height - pair_gap - height_a`
- `y_b = y_a + height_a + pair_gap`
- both panes share the same `x` and `width`

Validation rules:

- `pair_total_height` must be large enough that both computed pane heights are at least `1`
- `pair_gap` may be `0` but not negative
- invalid computed geometry should fail before creating any panes

### Config model

Add pair-specific defaults in `settings.py`, for example:

- pair top
- pair right
- pair width
- pair total height
- pair gap
- pair title prefix

These values should be environment-overridable in the same style as the current single-floating defaults.

Do not derive pair geometry from inline shell constants.

## Title Strategy

### Launch-time title

Do not block creation on semantic title quality.

For pair mode, create panes first with deterministic placeholder names:

- pane A: `cdx:a`
- pane B: `cdx:b`

Then rename after creation using pane IDs.

This avoids delaying pane startup and makes the panes distinguishable immediately, even before semantic extraction finishes.

### Final title

After creation, compute and apply semantic titles for each pane.

The extractor should prefer intent-based titles, not token slicing. Weak prompts such as `1+2=...` must map to a meaningful title such as `Math Check`, not `1 2`.

P0 rules:

- explicit per-pane title override, when added later, wins
- otherwise semantic extraction runs on the pane prompt source
- floating title prefix is applied after semantic resolution
- rename failures should not kill the pane; they should leave the placeholder name in place and report the failure in the outer result

## Architecture

### Preferred P0 design

Keep the implementation mostly in `bin/codex_wp`.

Flow:

1. Parse and strip pair-specific flags.
2. Validate that pair mode owns exactly two prompt sources.
3. Load config defaults for pair geometry and title behavior.
4. Validate:
   - `zellij` exists
   - an active zellij session exists
   - any prompt files are readable
5. Build two recursive inner commands:
   - pane A: `bin/codex_wp exec <shared-inner-args...> <prompt-a>`
   - pane B: `bin/codex_wp exec <shared-inner-args...> <prompt-b>`
6. Resolve geometry for the selected pair layout from the active zellij viewport.
7. Create pane A with placeholder title `cdx:a`.
8. Create pane B with placeholder title `cdx:b`.
9. Rename each pane by `pane_id` to its semantic title.
10. Emit outer launch metadata.

### Why not launch both panes in parallel in P0

Sequential launch is the better default in P0:

- slot ordering is deterministic
- failure reporting is simpler
- dry-run output matches runtime order
- test fixtures stay simpler

Parallel creation can be revisited later if startup latency becomes a real problem.

## Failure Model

### Validation failures before creation

Fail early and create nothing when:

- pane A or pane B prompt source is missing
- both `--a-prompt` and `--a-file` are set
- both `--b-prompt` and `--b-file` are set
- a prompt file is unreadable
- the pair layout key is unknown
- no active zellij session exists

These should exit with code `2` for argument or contract errors and code `1` for environment/runtime preconditions such as missing session state.

### Partial creation failures

If pane A is created and pane B fails:

- keep pane A open by default
- return a partial-failure result from the outer command
- do not silently close pane A

This is the safer operator behavior.

An explicit rollback option can be added later if there is a real need.

Recommended exit code for this case:

- exit `3` when at least one pane was created but the pair launch did not complete

### Rename failures

If creation succeeds but rename fails:

- leave the pane running
- keep the placeholder title
- report the rename failure in outer metadata or stderr

Rename is a presentation step, not a launch blocker.

Recommended exit behavior for this case:

- exit `0`
- mark the affected pane state as `rename_failed`

## Output Format

The outer command should have an explicit result contract.

### Default text output

Follow this format precisely.

```text
mode=zellij-floating-pair layout=<layout-key>
pane[a]=<pane-id> title="<final-title-a>" state=<created|renamed|rename_failed>
pane[b]=<pane-id> title="<final-title-b>" state=<created|renamed|rename_failed>
```

### Recommended exit codes

Follow this mapping precisely.

```text
0 = both panes created; rename may still be degraded and must be reflected in pane state
1 = runtime or environment failure before creation (eg. zellij missing, no active session)
2 = argument, prompt-source, layout-key, or geometry validation failure
3 = partial creation failure after at least one pane was opened
```

### JSON output

Use a dedicated outer flag:

- `--zellij-pair-json`

Do not reuse bare `--json` for the outer wrapper result because `--json` is already meaningful as a shared inner `codex exec` flag.

Follow this format precisely.

```json
{
  "mode": "zellij-floating-pair",
  "layout": "top-right-double",
  "panes": [
    {
      "slot": "a",
      "pane_id": "terminal_31",
      "initial_title": "cdx:a",
      "final_title": "cdx: Proxy Retry Review",
      "state": "renamed"
    },
    {
      "slot": "b",
      "pane_id": "terminal_32",
      "initial_title": "cdx:b",
      "final_title": "cdx: Auth Cooldown Check",
      "state": "renamed"
    }
  ]
}
```

## Required Steps

### 1. Lock the P0 scope

Ship only:

- exactly two panes
- `exec` only
- named pair layouts
- per-pane prompt text or prompt file
- shared inner args

Do not add:

- arbitrary pane counts
- arbitrary per-pane shell commands
- per-pane geometry CLI flags
- manifest files

### 2. Add pair config defaults

Extend [`src/cdx_proxy_cli_v2/config/settings.py`](/home/pets/TOOLS/cdx_proxy_cli_v2/src/cdx_proxy_cli_v2/config/settings.py) with pair-specific defaults and env overrides.

Rules:

- keep names consistent with the current single-floating config style
- keep all default geometry values in config
- keep the floating title prefix configurable

### 3. Extend `bin/codex_wp` argument parsing

Add a dedicated pair preprocessing block that:

- extracts `--zellij-floating-pair`
- extracts `--pair-layout`
- extracts `--a-prompt`
- extracts `--a-file`
- extracts `--b-prompt`
- extracts `--b-file`
- extracts `--zellij-pair-json`
- leaves the remaining shared inner args untouched

### 4. Implement prompt source loading

Add a small helper path that:

- validates source exclusivity per pane
- reads prompt files before any pane creation
- preserves literal inline prompt text

### 5. Implement pair geometry resolution

Add a layout resolver that:

- reads active zellij dimensions from `list-tabs --json --state --dimensions`
- computes pane A and pane B geometry from config-backed pair defaults
- centralizes layout math in one place

### 6. Implement create-then-rename flow

For each pane:

1. launch with placeholder title
2. capture returned `pane_id`
3. compute final semantic title
4. rename by `pane_id`

The outer command should then print text or JSON metadata.

### 7. Add tests

Add or update tests for:

- pair mode argument validation
- prompt file loading
- dry-run prints both commands
- pair layout resolves expected geometry
- both placeholder names are used at creation time
- both rename commands target the correct returned pane IDs
- semantic titles are resolved independently per pane
- partial failure reporting when pane B creation fails after pane A succeeds

### 8. Validate in a live zellij session

Run a real pair launch and verify:

- both panes appear in the intended positions
- placeholder titles appear immediately
- final semantic titles replace them
- prompts remain isolated to the correct pane
- the outer output reports both pane IDs correctly

## Validation

### Automated

Required automated checks before handoff:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
bash -n bin/codex_wp
python3 -m pytest -q tests/integration/test_codex_wp_green_path.py -k zellij
make test-integration-codex-wp
make test-e2e
```

### Manual

Run inside a real zellij session and verify at least these scenarios:

1. two inline prompts
2. one inline prompt plus one prompt file
3. semantic titles differ correctly between panes
4. pane B creation failure leaves pane A intact and reports partial failure
5. dry-run performs no side effects

## Notes

- This plan intentionally rejects a "mini-language in one shell string" API.
- This plan intentionally rejects arbitrary `N` panes in P0.
- If pair mode proves insufficient later, the next step should be a manifest-based orchestration layer rather than ad hoc repeated flags.
- The pair API should stay narrow enough that `codex-review-v2` or another caller can invoke it without complex shell quoting logic.
