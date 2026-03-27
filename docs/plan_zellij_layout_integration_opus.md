# Planning: Zellij Layout Integration for codex_wp (Revised)

## Overview

Add **optional zellij terminal multiplexer integration** to `codex_wp` for flexible pane layouts when running Codex reviews. The wrapper stays Bash; zellij orchestration lives in a thin Python helper. 100% backward compatible — no zellij flags means identical behavior to today.

---

## Design Decisions

### Keep codex_wp as Bash

The current 60-line Bash wrapper (`bin/codex_wp`) is clean, tested (364-line green-path integration test), and uses process semantics (`eval`, `exec`) that are natural in shell. Rewriting it in Python adds regression risk for no gain.

**Approach:** The Bash wrapper gains a pre-processing loop for `--zellij-*` flags. When any are present, it delegates to a Python helper (`cdx zellij-launch`) that handles tab creation, layout rendering, and command dispatch. When no zellij flags are present, behavior is identical to today.

### Tab-level orchestration only

The original plan included `--zellij-new-pane` (create pane in current tab) but left its split direction, placement, and layout interaction unspecified. Pane-level control is a different abstraction that complicates the API without a concrete use case.

**Cut:** `--zellij-new-pane` and `--zellij-pane-count` are removed. Pane count is an inherent property of the chosen layout template. If pane-level control is needed later, it can be added as a separate feature.

### No separate renderer module

Five small KDL templates with `{{VAR}}` substitution do not justify a dedicated `renderer.py`. A single `render_layout()` function inside `layouts.py` is sufficient.

---

## Current State

### codex_wp (Bash Wrapper)

**Location:** `bin/codex_wp` (60 lines)

**Current behavior:**
1. Resolves `cdx` and `codex` binaries
2. Sets up proxy environment (`eval "$(cdx proxy --print-env-only)"`)
3. Handles `-p` shorthand for exec subcommand
4. Executes `codex` with injected `openai_base_url`

**Test coverage:** `tests/integration/test_codex_wp_green_path.py` (364 lines, 10 E2E assertions)

---

## Proposed Architecture

### Module Structure

```
cdx_proxy_cli_v2/
├── bin/
│   └── codex_wp                    # Bash wrapper (enhanced, not rewritten)
├── src/cdx_proxy_cli_v2/
│   ├── cli/
│   │   └── main.py                 # Existing cdx CLI (gains zellij-launch subcommand)
│   ├── zellij/                     # NEW: zellij integration module
│   │   ├── __init__.py
│   │   ├── client.py               # Zellij CLI wrapper + availability check
│   │   └── layouts.py              # KDL templates, rendering, and layout registry
│   └── layouts/                    # NEW: KDL template files
│       ├── default.kdl             # 3 panes vertical (stacked)
│       ├── horizontal.kdl          # 3 panes side-by-side
│       ├── main-vertical.kdl       # Main left, stack right
│       ├── main-horizontal.kdl     # Main top, stack bottom
│       └── single.kdl              # 1 pane only
```

### Data Flow

```
User runs:
  codex_wp --zellij-new-tab "Review-1" --zellij-layout main-vertical -C /repo review ...

bin/codex_wp:
  1. Extracts --zellij-* flags from argv
  2. Detects zellij flags present → delegates to Python helper
  3. Calls: cdx zellij-launch --tab "Review-1" --layout main-vertical \
            -- codex_wp -C /repo review ...
     (the recursive codex_wp call has no zellij flags → runs normally)

cdx zellij-launch:
  1. Checks zellij availability (binary + active session)
  2. Renders KDL layout template with variables
  3. Writes temp .kdl file
  4. Creates tab: zellij action new-tab --layout /tmp/xxx.kdl --name "Review-1"
  5. If --zellij-send-command: sends the codex_wp command to pane
  6. If --zellij-focus: focuses the new tab
  7. Cleans up temp file
```

---

## CLI Interface

### New Optional Flags (on codex_wp)

| Flag | Description | Default | Priority |
|------|-------------|---------|----------|
| `--zellij-new-tab <name>` | Create new zellij tab with given name | (none — triggers zellij mode) | P0 |
| `--zellij-layout <name>` | Layout template: `default`, `horizontal`, `main-vertical`, `main-horizontal`, `single` | `default` | P0 |
| `--zellij-send-command` | Send command to pane instead of running locally | false | P0 |
| `--zellij-focus` | Focus the new tab after creation | false | P1 |
| `--zellij-cwd <path>` | Working directory for new tab | current directory | P1 |
| `--zellij-dry-run` | Print generated KDL and zellij commands without executing | false | P0 |

### Removed from Original Plan

| Flag | Reason |
|------|--------|
| `--zellij-new-pane` | Underspecified; no concrete use case; complicates API |
| `--zellij-pane-count <n>` | Contradicts template system — pane count is layout property |
| `--zellij-main-size <n>` | YAGNI — 60% default covers 95% of cases; add later if needed |

### Usage Examples

```bash
# 1. Current behavior (unchanged, no zellij flags)
codex_wp -C /repo review --uncommitted -

# 2. New tab with default vertical layout
codex_wp --zellij-new-tab "Review-1" -C /repo review --uncommitted -

# 3. Horizontal layout (side-by-side panes)
codex_wp --zellij-new-tab "Review-H" --zellij-layout horizontal -C /repo review --uncommitted -

# 4. Main pane + 2 stacked, with focus
codex_wp --zellij-new-tab "Review-MV" --zellij-layout main-vertical --zellij-focus -C /repo review --uncommitted -

# 5. Send command to pane (headless mode for codex-review-v2)
codex_wp --zellij-new-tab "Review-Headless" --zellij-send-command -C /repo review --uncommitted -

# 6. Dry run — see what would happen without executing
codex_wp --zellij-new-tab "Test" --zellij-layout main-vertical --zellij-dry-run -C /repo review --uncommitted -
```

---

## Layout Templates

### default.kdl (3 panes vertical)

```kdl
layout {
  cwd "{{CWD}}"
  tab name="{{TAB_NAME}}" focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane name="{{PANE_1}}"
    pane name="{{PANE_2}}"
    pane name="{{PANE_3}}"
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

```
┌─────────────────┐
│     pane 1      │
├─────────────────┤
│     pane 2      │
├─────────────────┤
│     pane 3      │
└─────────────────┘
```

### horizontal.kdl (3 panes side-by-side)

```kdl
layout {
  cwd "{{CWD}}"
  tab name="{{TAB_NAME}}" focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane split_direction="vertical" {
      pane name="{{PANE_1}}"
      pane name="{{PANE_2}}"
      pane name="{{PANE_3}}"
    }
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

```
┌────────┬────────┬────────┐
│ pane 1 │ pane 2 │ pane 3 │
└────────┴────────┴────────┘
```

### main-vertical.kdl (main left, stack right)

```kdl
layout {
  cwd "{{CWD}}"
  tab name="{{TAB_NAME}}" focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane split_direction="vertical" {
      pane name="{{PANE_1}}" size="60%"
      pane {
        pane name="{{PANE_2}}"
        pane name="{{PANE_3}}"
      }
    }
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

```
┌──────────────┬───────────┐
│              │  pane 2   │
│   pane 1     ├───────────┤
│   (60%)      │  pane 3   │
│              │           │
└──────────────┴───────────┘
```

### main-horizontal.kdl (main top, stack below)

```kdl
layout {
  cwd "{{CWD}}"
  tab name="{{TAB_NAME}}" focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane name="{{PANE_1}}" size="60%"
    pane split_direction="vertical" {
      pane name="{{PANE_2}}"
      pane name="{{PANE_3}}"
    }
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

```
┌──────────────────────────┐
│         pane 1           │
│         (60%)            │
├──────────────┬───────────┤
│   pane 2     │  pane 3   │
└──────────────┴───────────┘
```

### single.kdl (1 pane only)

```kdl
layout {
  cwd "{{CWD}}"
  tab name="{{TAB_NAME}}" focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane name="{{PANE_1}}"
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

---

## Implementation Details

### ZellijClient (client.py)

```python
class ZellijClient:
    """Thin wrapper around zellij CLI. All methods raise ZellijError on failure."""

    @staticmethod
    def check_available() -> None:
        """Verify zellij binary exists and a session is active.
        Raises ZellijNotFound or ZellijNoSession with actionable message."""

    def create_tab_from_layout(self, name: str, layout_path: Path, cwd: str) -> None:
        """Create a new tab using a rendered KDL layout file.
        Idempotent: closes existing tab with same name first."""

    def focus_tab(self, name: str) -> None:
        """Focus an existing tab by name."""

    def send_command_to_pane(self, tab_name: str, pane_index: int, command: str) -> None:
        """Write a command string to a specific pane in a tab."""

    def close_tab_if_present(self, name: str) -> None:
        """Close tab by name. No-op if tab doesn't exist."""
```

**Idempotency rule:** `create_tab_from_layout` always calls `close_tab_if_present` first. This prevents duplicate tabs from repeated runs and makes the workflow safe to retry.

### Layout Rendering (layouts.py)

```python
LAYOUTS_DIR = Path(__file__).parent.parent / "layouts"

VALID_LAYOUTS = {"default", "horizontal", "main-vertical", "main-horizontal", "single"}

def render_layout(name: str, variables: dict[str, str]) -> str:
    """Render a KDL template with {{VAR}} substitution.

    Args:
        name: Layout name (must be in VALID_LAYOUTS)
        variables: Dict of template variables (CWD, TAB_NAME, PANE_1, etc.)

    Returns:
        Rendered KDL string ready to write to a temp file.

    Raises:
        ValueError: Unknown layout name.
        FileNotFoundError: Missing .kdl template.
    """
    if name not in VALID_LAYOUTS:
        raise ValueError(f"Unknown layout: {name!r}. Valid: {', '.join(sorted(VALID_LAYOUTS))}")
    template = (LAYOUTS_DIR / f"{name}.kdl").read_text()
    for key, value in variables.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template
```

### Error Handling & Fallback

| Condition | Behavior |
|-----------|----------|
| `zellij` binary not found | Exit with: `codex_wp: zellij not found. Install it or remove --zellij-* flags.` |
| No active zellij session | Exit with: `codex_wp: no active zellij session. Run inside zellij or remove --zellij-* flags.` |
| Unknown layout name | Exit with: `codex_wp: unknown layout 'X'. Valid: default, horizontal, ...` |
| Tab creation fails | Exit with zellij's stderr and exit code |
| `--zellij-dry-run` | Print rendered KDL + planned zellij commands to stdout, exit 0 |

No silent fallback to non-zellij mode. If the user asks for zellij and it's not available, fail loudly. Silent degradation hides problems.

---

## Changes to bin/codex_wp

Minimal additions to the existing Bash script:

```bash
# After existing -p handling loop, add zellij flag extraction:
zellij_args=()
passthrough_args=()
for arg in "${args[@]}"; do
  case "$arg" in
    --zellij-*) zellij_args+=("$arg") ;;
    *)          passthrough_args+=("$arg") ;;
  esac
done

# If zellij flags present, delegate to Python helper
if [[ ${#zellij_args[@]} -gt 0 ]]; then
  exec "$cdx_bin" zellij-launch "${zellij_args[@]}" -- "${passthrough_args[@]}"
fi

# Otherwise: existing behavior unchanged
```

This is ~10 lines added to the existing script. No rewrite needed.

---

## Integration with codex-review-v2

```python
# In codex-review-v2 launch command
codex_wp_cmd = [
    "codex_wp",
    "--zellij-new-tab", run_state["tab_name"],
    "--zellij-layout", "main-vertical",
    "--zellij-send-command",
    "-C", str(target),
    "review", "--uncommitted", "-"
]
```

---

## Testing Strategy

### Unit Tests (automated, CI-safe)

| Test | What it verifies |
|------|-----------------|
| `test_render_layout_default` | Default template renders with all variables substituted |
| `test_render_layout_all_templates` | Every .kdl file in layouts/ renders without leftover `{{` markers |
| `test_render_layout_unknown` | Unknown layout name raises ValueError |
| `test_valid_layouts_matches_files` | `VALID_LAYOUTS` set matches actual .kdl files on disk |
| `test_zellij_flag_parsing` | codex_wp correctly separates `--zellij-*` flags from passthrough args |
| `test_dry_run_output` | `--zellij-dry-run` prints KDL and commands without subprocess calls |

### Mocked Integration Tests (automated, CI-safe)

| Test | What it verifies |
|------|-----------------|
| `test_zellij_not_found` | Clear error when zellij binary missing |
| `test_zellij_no_session` | Clear error when no active session |
| `test_create_tab_idempotent` | close-then-create called in sequence |
| `test_send_command_to_pane` | Correct zellij CLI args constructed |
| `test_backward_compat_no_flags` | No zellij flags → existing green-path behavior unchanged |

### Manual E2E (requires live zellij session)

| Test | What it verifies |
|------|-----------------|
| All 5 layouts render correctly | Visual pane arrangement matches diagrams |
| `--zellij-send-command` delivers command | Pane receives and executes the codex command |
| `--zellij-focus` switches to new tab | Tab gains focus after creation |
| Duplicate tab name handled | Second run closes old tab, creates new one |

---

## Implementation Order

| Step | Scope | Depends On |
|------|-------|------------|
| 1 | Create `layouts/*.kdl` template files | — |
| 2 | Implement `zellij/layouts.py` (render function + registry) | Step 1 |
| 3 | Unit tests for layout rendering | Step 2 |
| 4 | Implement `zellij/client.py` (ZellijClient + availability check) | — |
| 5 | Mocked integration tests for ZellijClient | Step 4 |
| 6 | Add `zellij-launch` subcommand to `cli/main.py` | Steps 2, 4 |
| 7 | Enhance `bin/codex_wp` with `--zellij-*` flag extraction (~10 lines) | Step 6 |
| 8 | Integration test: backward compatibility with no zellij flags | Step 7 |
| 9 | `--zellij-dry-run` support | Step 6 |
| 10 | Manual E2E validation in live zellij session | Step 7 |

---

## Summary Table

| Feature | Status | Priority |
|---------|--------|----------|
| `--zellij-new-tab` | Planned | P0 |
| `--zellij-layout` | Planned | P0 |
| `--zellij-send-command` | Planned | P0 |
| `--zellij-dry-run` | Planned | P0 |
| KDL template system | Planned | P0 |
| Zellij availability check | Planned | P0 |
| Idempotent tab handling | Planned | P0 |
| Backward compatibility | Required | P0 |
| `--zellij-focus` | Planned | P1 |
| `--zellij-cwd` | Planned | P1 |
| Testing (unit + mocked) | Planned | P0 |

---

## Key Differences from Original Plan

| Area | Original | This Revision |
|------|----------|---------------|
| codex_wp language | Rewrite to Python | Keep Bash, add ~10 lines |
| Module count | 3 files (client, layouts, renderer) | 2 files (client, layouts) |
| CLI flags | 8 flags | 6 flags (dropped pane-count, new-pane, main-size; added dry-run) |
| Error handling | Not specified | Explicit fail-loud strategy with actionable messages |
| Idempotency | close_tab listed but unused | close-before-create as default behavior |
| Testing | Not specified | Unit, mocked integration, and manual E2E plan |
| Dry-run support | Not included | P0 flag for debugging |

---
