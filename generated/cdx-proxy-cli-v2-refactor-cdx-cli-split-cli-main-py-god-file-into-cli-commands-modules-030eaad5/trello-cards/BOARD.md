# Board: cdx CLI Refactor

| ID | Title | SP | Hrs | Depends | Status |
|----|-------|:--:|:---:|---------|--------|
| 0001 | Split main.py into cli/commands/ modules | 2 | 2 | — | 🔵 todo |
| 0002 | Declarative settings resolver in settings.py | 2 | 2 | — | 🔵 todo |
| 0003 | Unify --force/--replace flags + add help epilogs | 1 | 1 | 0001 | 🔵 todo |
| 0004 | Run tests and verify no regressions | 1 | 1 | 0001,0002,0003 | 🔵 todo |

**Total: 6 SP / 6 hours**

### Dependency order

```
0001 ──┐
       ├──→ 0003 ──┐
0002 ──┤           ├──→ 0004
       └───────────┘
```

Cards 0001 and 0002 can run in parallel. Card 0003 needs 0001 done. Card 0004 runs last.
