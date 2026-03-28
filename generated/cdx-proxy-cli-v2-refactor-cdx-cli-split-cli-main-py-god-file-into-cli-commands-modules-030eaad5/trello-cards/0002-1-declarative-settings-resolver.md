# Card 0002: Declarative settings resolver in settings.py

| Field | Value |
|-------|-------|
| Phase | Phase 1: Implementation |
| Story Points | 2 |
| Estimated Hours | 2 |
| Depends On | None |

## Intent

Replace the 200+ line repetitive `build_settings()` with a declarative spec table + generic resolver loop. Same behavior, 80% less code.

## Files

- `src/cdx_proxy_cli_v2/config/settings.py`

## Implementation Tasks

- [ ] Define a `_SETTING_SPEC` list of tuples: `(field_name, env_key, default, parser, min_value)`
- [ ] Write a generic `_resolve_setting(cli_value, merged_env, env_key, default, parser, min_value)` helper
- [ ] Rewrite `build_settings()` to loop over `_SETTING_SPEC` instead of repeating the same pattern 15+ times
- [ ] Keep `Settings` dataclass, `build_settings()` signature, and all public exports unchanged
- [ ] Keep special-case logic (e.g. `normalize_upstream`, management key "None" stripping, env file loading) as explicit code outside the loop

## Acceptance Criteria

- [ ] `build_settings()` is under 60 lines (from 200+)
- [ ] All existing `Settings` fields resolve to identical values for the same inputs
- [ ] `cdx status` and `cdx proxy --print-env-only` produce identical output before and after
- [ ] No new public API surface

## Rollback

- Revert `settings.py` from git.
