# Simplicity Scout Report

- Runtime behavior is stable, but structural simplicity is reduced by legacy parallel abstractions.
- The lifecycle path is the main active complexity hotspot.

## Findings

1. **P1 — dead parallel proxy abstractions still exist**
   - References: `src/cdx_proxy_cli_v2/proxy/management.py:39`, `src/cdx_proxy_cli_v2/proxy/runtime.py:15`

2. **P1 — `start_service` combines too many concerns**
   - Reference: `src/cdx_proxy_cli_v2/runtime/service.py:339`

3. **P2 — legacy token-based “current account” matching looks stale**
   - References: `src/cdx_proxy_cli_v2/observability/collective_dashboard.py:174`, `src/cdx_proxy_cli_v2/cli/main.py:326`

## Top Recommendation

Reduce active risk first; structural cleanup is acknowledged but not cardized in this run.
