# Card 0004: Run tests and verify no regressions

| Field | Value |
|-------|-------|
| Phase | Phase 2: Verification |
| Story Points | 1 |
| Estimated Hours | 1 |
| Depends On | 0001, 0002, 0003 |

## Intent

Run the full test suite and smoke-test every `cdx` subcommand to confirm the refactor didn't break anything.

## Files

- No files to edit — verification only

## Implementation Tasks

- [ ] Run `cd /home/pets/TOOLS/cdx_proxy_cli_v2 && python -m pytest tests/ -q` — all pass
- [ ] Run `cdx --help` — shows all subcommands
- [ ] Run `cdx proxy --help` — shows examples epilog
- [ ] Run `cdx trace --help` — shows `--replace`, shows examples epilog
- [ ] Run `cdx trace --force` (with proxy running) — replaces existing trace
- [ ] Run `cdx doctor --help` — shows `--probe`/`--fix`/`--repair`
- [ ] Run `cdx status` — shows proxy status
- [ ] Run `cdx rotate --dry-run` — dry run works
- [ ] Run `cdx all --json` — JSON output valid
- [ ] Grep for stale imports or broken module references

## Acceptance Criteria

- [ ] All tests pass
- [ ] Every `cdx <cmd> --help` shows examples
- [ ] `cdx trace --force` works as alias for `--replace`
- [ ] No import errors or broken references

## Rollback

- No rollback needed — this card makes no changes.
