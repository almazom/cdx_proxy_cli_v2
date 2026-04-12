# Board: Codex Proxy Resilience And Review-Path Hardening

| ID | Title | SP | Hrs | Depends | Status |
|----|-------|:--:|:---:|---------|--------|
| 0001 | Build the failure taxonomy and reproduce the degraded-state matrix | 2 | 2 | — | 🔵 todo |
| 0002 | Bound `/health` and management-plane refresh under degraded auth state | 3 | 3 | 0001 | ⚪ backlog |
| 0003 | Harden downstream write path and classify BrokenPipe disconnects | 2 | 2 | — | 🔵 todo |
| 0004 | Refine auth rotation and auto-heal policy for mixed healthy/degraded pools | 3 | 3 | — | 🔵 todo |
| 0005 | Add review-path diagnostics for model refresh and child-exit stalls | 3 | 3 | 0001,0002,0004 | ⚪ backlog |
| 0006 | Expose operator triage signals in debug, trace, and CLI health flows | 2 | 2 | 0002,0003,0004,0005 | ⚪ backlog |
| 0007 | Update recovery runbooks for degraded pool and review-path incidents | 1 | 1 | 0006 | ⚪ backlog |
| 0008 | Run the regression and live-smoke verification matrix | 3 | 3 | 0002,0003,0004,0005,0006,0007 | ⚪ backlog |

**Total: 19 SP / 19 hours**

### Dependency order

```text
0001 ──> 0002 ──┐
                ├──> 0005 ──> 0006 ──> 0007 ──> 0008
0004 ───────────┘      ^
                       |
0003 ──────────────────┘
```

Cards `0001`, `0003`, and `0004` are intentionally parallel-safe starting points.
