# Plan: codex_wp Floating Window Review Follow-up (Opus Review)

## Overview

Four concrete problems were found during a review of the floating-window / Zellij work in `bin/codex_wp` (1 305 lines, 34 KB) and its supporting modules. This plan addresses them in dependency order, from most dangerous to least.

## Findings Summary

| # | Issue | Severity | Blast Radius |
|---|-------|----------|--------------|
| 1 | `--help` launches real Zellij panes | **Critical** | Any operator exploring flags in a live session |
| 2 | `-p` collision shadows upstream `--profile` | **High** | Any `codex_wp exec -p <profile>` call |
| 3 | Trace singleton kills arbitrary PIDs | **High** | `cdx trace --replace` on long-lived hosts |
| 4 | Integration gate is red | **Medium** | CI confidence; may or may not be caused by items 1–3 |

---

## Task 1 — Make `--help` Side-Effect Free

**Priority:** P0 — safety regression, blocks operator discovery of new features.

### Root Cause

`bin/codex_wp` has **zero help handling** in its argument parser (lines 106–239). The `while [[ $# -gt 0 ]]` loop never matches `--help` or `-h`, so those tokens fall through to the Zellij dispatch block (lines 981–1285) where real `zellij run` / `zellij action new-pane` commands execute unconditionally.

### Fix

Add a **first-pass help scan** before the main parse loop:

```bash
# ── early help gate (before any side effects) ──────────────
for arg in "$@"; do
  case "$arg" in
    -h|--help) _show_wrapper_help; exit 0 ;;
  esac
done
```

Implement `_show_wrapper_help()` that prints:

1. A short wrapper synopsis covering all `--zellij-*` flags, pair-mode geometry flags, and prompt shortcut flags.
2. A separator line.
3. The upstream `codex --help` output (captured via subshell, not exec'd).

This keeps the function pure: no Zellij calls, no process spawning, no state changes.

### Scope of Change

- `bin/codex_wp` — add ~40 lines near the top (before line 106).
- No Python changes.

### Tests

| Case | Assert |
|------|--------|
| `bin/codex_wp --help` | prints wrapper section + upstream help, exit 0 |
| `bin/codex_wp --zellij-floating --help` | same output, exit 0, **no** pane created |
| `bin/codex_wp --zellij-new-tab --help` | same output, exit 0, **no** tab created |
| `bin/codex_wp --zellij-floating-pair --help` | same output, exit 0, **no** pair error |
| `bin/codex_wp review --help` | prints wrapper section + upstream review help |

Validation: grep the test output for `zellij` subprocesses — must be zero.

---

## Task 2 — Remove the `-p` Collision

**Priority:** P1 — silent compatibility regression against upstream Codex CLI.

### Root Cause

Lines 230–234 of `bin/codex_wp`:

```bash
-p)
  prompt_arg="$2"
  shift 2 || die "codex_wp: -p requires a prompt argument"
  args+=("exec" "$prompt_arg")
  ;;
```

This consumes `-p` as a prompt shortcut and auto-prepends `exec`, which shadows the real Codex `-p/--profile` flag. Result: `bin/codex_wp exec -p test-profile` fails with an unexpected-argument error.

### Fix

1. **Remove the `-p)` case entirely** from the wrapper parser.
2. If a quick-prompt shortcut is still wanted, introduce a wrapper-namespaced long flag: `--wp-prompt` or `--quick` (TBD — should not collide with any current or future upstream flag).
3. Document explicitly: *all single-letter flags are reserved for upstream Codex pass-through*.

### Scope of Change

- `bin/codex_wp` — remove 4 lines, optionally add a new long-flag case.
- Update any docs or comments that reference `-p`.

### Tests

| Case | Assert |
|------|--------|
| `bin/codex_wp exec -p test-profile` | passes through to codex, no wrapper error |
| `bin/codex_wp review -p some-profile` | passes through cleanly |
| `bin/codex_wp --wp-prompt "do X"` | (if added) expands to `exec "do X"` |

---

## Task 3 — Harden Trace Singleton PID Replacement

**Priority:** P1 — data-safety risk on production hosts.

### Root Cause

`src/cdx_proxy_cli_v2/runtime/singleton.py` lines 77–82:

```python
existing_pid = _read_pid(pid_path)
if existing_pid is not None and _is_pid_running(existing_pid):
    if kill_existing:
        killed_existing = _terminate_pid(existing_pid)
```

`_is_pid_running()` uses `os.kill(pid, 0)` which only checks "a process with this PID exists and is owned by us". It does **not** verify that the process is actually a trace/proxy process. On a long-lived host, the original process may have exited and the OS may have recycled the PID to an unrelated process.

`_terminate_pid()` (lines 38–49) then sends SIGTERM → waits 1 s → SIGKILL with no identity check.

### Fix

**Option A (recommended): Store process identity in the pid file.**

Change the pid file format from bare PID to:

```
<pid> <process_start_time> <expected_cmdline_prefix>
```

Before killing, verify:

1. PID is running (`os.kill(pid, 0)`).
2. Process start time matches (read from `/proc/<pid>/stat` field 22, or `psutil.Process(pid).create_time()`).
3. Cmdline prefix matches (read from `/proc/<pid>/cmdline`).

If any check fails, treat the pid file as stale → remove it, do not kill.

**Option B (simpler): Use `fcntl.flock()` advisory lock.**

Hold an advisory lock on the pid file for the lifetime of the owning process. A new instance trying `--replace` attempts `flock(LOCK_EX | LOCK_NB)`:

- If it succeeds → old process is gone, pid file is stale, safe to overwrite.
- If it fails → old process is alive, send SIGTERM to that PID (lock holder identity is implicitly verified).

Option A is more explicit and auditable. Option B is simpler but less portable outside Linux.

### Additional Cleanup

- Replace `sys.exit()` inside `singleton.py` with a raised `SingletonError` exception — let the caller decide exit behavior.

### Scope of Change

- `src/cdx_proxy_cli_v2/runtime/singleton.py` — rewrite `acquire_singleton_lock()` and `_terminate_pid()`.
- Callers of `acquire_singleton_lock()` — add exception handling for `SingletonError`.

### Tests

| Case | Assert |
|------|--------|
| Stale pid file (process exited) | lock acquired, no kill attempt |
| Recycled PID (different process) | lock acquired, stale file removed, **no kill** |
| Live trace process + `--replace` | SIGTERM sent, lock acquired after exit |
| Live trace process + no `--replace` | `SingletonError` raised, no kill |

---

## Task 4 — Recover the Integration Green Path

**Priority:** P1 — gate must be green before any of the above ships.

### Symptom

`make test-integration-codex-wp` fails with:

```
subprocess.TimeoutExpired: ... cdx proxy ... --print-env-only ... timed out after 30.0 seconds
```

The spawned proxy PID disappears immediately and the per-test log is empty.

### Investigation Steps

1. **Reproduce in isolation:**
   ```bash
   cdx proxy --auth-dir /tmp/test-auths --upstream http://127.0.0.1:9999 \
     --host 127.0.0.1 --port 0 --print-env-only
   ```
   Check exit code, stderr, and whether the PID file gets written.

2. **Instrument `_start_proxy()` in test fixture:** capture stderr alongside stdout; log child PID immediately after spawn.

3. **Check for port/resource conflict:** another proxy or test may be holding a resource the new one needs.

4. **Check whether Tasks 1–3 changes affect this path** — the proxy startup path is independent of Zellij, but the `-p` collision or singleton changes could interact if the test harness uses those code paths.

### Scope of Change

- Likely a test fixture adjustment or a small proxy startup bug.
- May need a retry/backoff in `_start_proxy()` if it's a race condition.
- If the root cause is in proxy startup itself, that fix goes here.

### Validation

```bash
make test-integration-codex-wp   # must pass
make test-e2e                     # must still pass (10 green)
```

---

## Dependency Graph

```
Task 1 (help safety)     ─┐
Task 2 (-p collision)     ─┼──▶  Task 4 (green path recovery)  ──▶  Final validation
Task 3 (singleton harden) ─┘
```

Tasks 1–3 are independent of each other and can be done in parallel.
Task 4 must come last because it is the integration gate that validates everything.

## Suggested Execution Order

If working sequentially:

1. **Task 1** — help safety (highest user-facing impact, pure shell change, fast to validate).
2. **Task 2** — `-p` removal (4-line deletion, quick win).
3. **Task 3** — singleton hardening (Python change, needs careful testing).
4. **Task 4** — green-path recovery (investigation-driven, may uncover further issues).
5. **Final gate:**
   ```bash
   cd /home/pets/TOOLS/cdx_proxy_cli_v2
   # Full CLI help sweep
   cdx --help && cdx proxy --help && cdx status --help && cdx doctor --help && \
   cdx stop --help && cdx trace --help && cdx logs --help && cdx limits --help && \
   cdx migrate --help && cdx reset --help && cdx rotate --help && cdx all --help && \
   cdx run-server --help
   # Integration + E2E
   make test-integration-codex-wp
   make test-e2e
   ```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Help scan breaks pass-through of `--help` to upstream subcommands | Medium | Medium | Test both wrapper help and `codex_wp exec --help` pass-through |
| Removing `-p` breaks operator muscle memory | Low | Low | Announce in changelog; add `--wp-prompt` replacement if needed |
| Singleton flock not portable to macOS | Medium | Low | Use Option A (proc-based) or feature-detect at import time |
| Green-path failure has a deeper root cause | Medium | High | Timebox investigation; if > 2 hours, escalate to a standalone bug |

## Exit Criteria

All of the following must be true before handoff:

- [ ] `bin/codex_wp --help` prints wrapper + upstream help with zero side effects
- [ ] `bin/codex_wp --zellij-floating --help` does not create a pane
- [ ] `bin/codex_wp exec -p <profile>` passes through to upstream Codex unchanged
- [ ] `cdx trace --replace` with a stale/recycled PID does **not** kill an unrelated process
- [ ] `singleton.py` raises an exception instead of calling `sys.exit()`
- [ ] `make test-integration-codex-wp` passes
- [ ] `make test-e2e` passes (10 green)
- [ ] Full CLI help sweep exits 0 for all commands
