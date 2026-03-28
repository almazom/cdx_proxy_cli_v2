# Cards Catalog

## cdx CLI Refactor — 4 cards, 6 SP, ~6 hours

| ID | Title | Phase | SP | Hrs | Depends On |
|----|-------|-------|:--:|:---:|------------|
| `0001` | Split main.py into cli/commands/ modules | Implementation | 2 | 2 | — |
| `0002` | Declarative settings resolver in settings.py | Implementation | 2 | 2 | — |
| `0003` | Unify --force/--replace flags + add help epilogs | Implementation | 1 | 1 | 0001 |
| `0004` | Run tests and verify no regressions | Verification | 1 | 1 | 0001,0002,0003 |

### Goal
Refactor cdx CLI for maintainability: split the God file, kill settings boilerplate, fix UX inconsistencies. No new features, no over-engineering. Full backward compat.
