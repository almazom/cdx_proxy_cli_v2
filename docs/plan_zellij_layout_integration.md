# Planning: Zellij Layout Integration for codex_wp

## Overview

This document outlines the plan to add **optional zellij terminal multiplexer integration** to `codex_wp` in the `cdx_proxy_cli_v2` project. The goal is to enable flexible pane layouts (horizontal, vertical, main-pane splits) when running Codex reviews, while maintaining 100% backward compatibility.

---

## Current State

### codex_wp (Current Bash Wrapper)

**Location:** `bin/codex_wp`

**Current behavior:**
1. Resolves `cdx` and `codex` binaries
2. Sets up proxy environment (`eval "$(cdx proxy --print-env-only)"`)
3. Executes `codex` with injected `openai_base_url`

**Current limitations:**
- No zellij integration
- No pane layout control
- Runs codex in current terminal context only

---

## Proposed Architecture

### New Module Structure

```
cdx_proxy_cli_v2/
├── bin/
│   └── codex_wp                    # Enhanced wrapper (Python-based)
├── src/cdx_proxy_cli_v2/
│   ├── cli/
│   │   ├── main.py                 # Existing cdx command
│   │   └── codex_wp.py             # NEW: codex_wp Python implementation
│   ├── zellij/                     # NEW: zellij integration module
│   │   ├── __init__.py
│   │   ├── client.py               # Zellij CLI wrapper
│   │   ├── layouts.py              # Layout templates & rendering
│   │   └── renderer.py             # KDL template engine (optional)
│   └── layouts/                    # NEW: KDL template files
│       ├── default.kdl             # 3 panes vertical (current behavior)
│       ├── horizontal.kdl          # 3 panes side-by-side
│       ├── main-vertical.kdl       # Main left, stack right
│       ├── main-horizontal.kdl     # Main top, stack bottom
│       └── single.kdl              # 1 pane only
```

---

## CLI Interface

### New Optional Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--zellij-new-tab <name>` | Create new zellij tab with given name | (none) |
| `--zellij-new-pane` | Create new pane in current tab | false |
| `--zellij-layout <name>` | Layout template: `default`, `horizontal`, `main-vertical`, `main-horizontal`, `single` | `default` |
| `--zellij-pane-count <n>` | Number of panes to create | 1 |
| `--zellij-focus` | Focus the new tab/pane after creation | false |
| `--zellij-send-command` | Send command to pane instead of running locally | false |
| `--zellij-cwd <path>` | Working directory for new tab/pane | current |
| `--zellij-main-size <n>` | Main pane size percentage (for main-* layouts) | 60 |

### Usage Examples

```bash
# 1. Current behavior (unchanged)
codex_wp -C /repo review --uncommitted -

# 2. New tab with default vertical layout
codex_wp --zellij-new-tab "Review-1" -C /repo review --uncommitted -

# 3. Horizontal layout (side-by-side)
codex_wp --zellij-new-tab "Review-H" --zellij-layout horizontal -C /repo review --uncommitted -

# 4. Main pane + 2 stacked (vertical split)
codex_wp --zellij-new-tab "Review-MV" --zellij-layout main-vertical --zellij-focus -C /repo review --uncommitted -

# 5. Send command to pane (headless mode)
codex_wp --zellij-new-tab "Review-Headless" --zellij-send-command -C /repo review --uncommitted -

# 6. Single pane in new tab
codex_wp --zellij-new-tab "Quick-Review" --zellij-layout single -C /repo review --uncommitted -
```

---

## Layout Templates

### default.kdl (3 panes vertical)

```kdl
layout {
  cwd {{CWD}}
  tab name={{TAB_NAME}} focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane name={{PANE_1}}
    pane name={{PANE_2}}
    pane name={{PANE_3}}
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

**Visual:**
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
  cwd {{CWD}}
  tab name={{TAB_NAME}} focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane split_direction="vertical" {
      pane name={{PANE_1}}
      pane name={{PANE_2}}
      pane name={{PANE_3}}
    }
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

**Visual:**
```
┌────────┬────────┬────────┐
│ pane 1 │ pane 2 │ pane 3 │
└────────┴────────┴────────┘
```

### main-vertical.kdl (main left, stack right)

```kdl
layout {
  cwd {{CWD}}
  tab name={{TAB_NAME}} focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane split_direction="vertical" {
      pane name={{PANE_1}} size={{MAIN_SIZE}}
      pane {
        pane name={{PANE_2}}
        pane name={{PANE_3}}
      }
    }
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

**Visual:**
```
┌──────────────┬───────────┐
│              │  pane 2   │
│    pane 1    ├───────────┤
│   (60%)      │  pane 3   │
│              │           │
└──────────────┴───────────┘
```

### main-horizontal.kdl (main top, stack below)

```kdl
layout {
  cwd {{CWD}}
  tab name={{TAB_NAME}} focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane name={{PANE_1}} size={{MAIN_SIZE}}
    pane {
      pane name={{PANE_2}}
      pane name={{PANE_3}}
    }
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

**Visual:**
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
  cwd {{CWD}}
  tab name={{TAB_NAME}} focus=true hide_floating_panes=true {
    pane size=1 borderless=true {
      plugin location="zellij:tab-bar"
    }
    pane name={{PANE_1}}
    pane size=1 borderless=true {
      plugin location="zellij:status-bar"
    }
  }
}
```

---

## Implementation Details

### Key Components

1. **ZellijClient** - Wraps zellij CLI commands
2. **LayoutRenderer** - Renders KDL templates with variables
3. **codex_wp.py** - Main entry point with argument parsing

### ZellijClient Methods

```python
class ZellijClient:
    def create_tab_from_layout(self, name: str, layout_kdl: str, cwd: str) -> None
    def focus_tab(self, name: str) -> None
    def send_command_to_pane(self, tab_name: str, pane_index: int, command: str) -> None
    def close_tab_if_present(self, name: str) -> None
```

### Template Rendering

```python
def render_layout(name: str, variables: dict) -> str:
    """Render KDL template with variable substitution."""
    template_path = LAYOUTS_DIR / f"{name}.kdl"
    content = template_path.read_text()
    for key, value in variables.items():
        content = content.replace(f"{{{{{key}}}}}", json.dumps(str(value)))
    return content
```

---

## Integration with codex-review-v2

The `codex-review-v2` tool can leverage these new flags:

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

## Summary Table

| Feature | Status | Priority |
|---------|--------|----------|
| `--zellij-new-tab` | Planned | P0 |
| `--zellij-new-pane` | Planned | P1 |
| `--zellij-layout` | Planned | P0 |
| `--zellij-focus` | Planned | P1 |
| `--zellij-send-command` | Planned | P0 |
| KDL template system | Planned | P0 |
| Backward compatibility | Required | P0 |

---
