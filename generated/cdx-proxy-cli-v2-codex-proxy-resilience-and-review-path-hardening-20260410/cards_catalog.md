# Cards Catalog

## Codex Proxy Resilience And Review-Path Hardening — 8 cards, 19 SP, ~19 hours

| ID | Title | Phase | SP | Hrs | Depends On |
|----|-------|-------|:--:|:---:|------------|
| `0001` | Build the failure taxonomy and reproduce the degraded-state matrix | Discovery | 2 | 2 | — |
| `0002` | Bound `/health` and management-plane refresh under degraded auth state | Implementation | 3 | 3 | 0001 |
| `0003` | Harden downstream write path and classify BrokenPipe disconnects | Implementation | 2 | 2 | — |
| `0004` | Refine auth rotation and auto-heal policy for mixed healthy/degraded pools | Implementation | 3 | 3 | — |
| `0005` | Add review-path diagnostics for model refresh and child-exit stalls | Implementation | 3 | 3 | 0001,0002,0004 |
| `0006` | Expose operator triage signals in debug, trace, and CLI health flows | Implementation | 2 | 2 | 0002,0003,0004,0005 |
| `0007` | Update recovery runbooks for degraded pool and review-path incidents | Documentation | 1 | 1 | 0006 |
| `0008` | Run the regression and live-smoke verification matrix | Verification | 3 | 3 | 0002,0003,0004,0005,0006,0007 |

### Goal

Turn the observed 2026-04-10 proxy degradation into a controlled, diagnosable, bounded failure mode. Keep the management plane responsive, stop noisy BrokenPipe fallout, reduce sticky false ejection, and make `codex_wp review` failures explainable.
