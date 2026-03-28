# Card 0003: Unify --force/--replace flags + add help epilogs

| Field | Value |
|-------|-------|
| Phase | Phase 1: Implementation |
| Story Points | 1 |
| Estimated Hours | 1 |
| Depends On | 0001 |

## Intent

Two small UX fixes: (a) add `--force` as an alias for `--replace` on `cdx trace`, and (b) add usage example epilogs to all subcommands.

## Files

- `src/cdx_proxy_cli_v2/cli/main.py` (or `cli/commands/` after card 0001)

## Implementation Tasks

- [ ] In trace parser: add `--force` as a hidden alias that sets the same `replace=True` destination
  ```python
  trace_parser.add_argument("--force", dest="replace", action="store_true", help=argparse.SUPPRESS)
  ```
- [ ] Add 2-line epilog examples to every subcommand that doesn't have one yet:
  - `status`: `cdx status --json`
  - `doctor`: `cdx doctor --probe`, `cdx doctor --fix`
  - `stop`: `cdx stop`
  - `trace`: `cdx trace --replace`, `cdx trace --limit 20`
  - `logs`: `cdx logs --lines 50`
  - `limits`: `cdx limits --tail 10`
  - `reset`: `cdx reset --state blacklist`, `cdx reset --name auth_001.json`
  - `rotate`: `cdx rotate --dry-run`
  - `all`: `cdx all --only weekly`
- [ ] Verify `cdx trace --force` works identically to `cdx trace --replace`
- [ ] Verify `cdx trace --help` still shows `--replace` (not `--force` — it's hidden)

## Acceptance Criteria

- [ ] `cdx trace --force` kills and replaces existing trace process (same as `--replace`)
- [ ] `cdx trace --replace` still works (backward compat)
- [ ] Every subcommand `--help` shows at least one usage example
- [ ] `proxy` epilog unchanged (already has examples)

## Rollback

- Revert the trace parser changes.
