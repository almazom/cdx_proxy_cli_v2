# Maintainability Scout Report

- Current HEAD is test-backed, but maintainability debt is concentrated in a few core orchestration files.
- Duplicate proxy/runtime abstractions and monolithic lifecycle logic are the main concerns.

## Findings

1. **P1 — duplicate proxy/runtime abstractions remain in tree**
   - References: `src/cdx_proxy_cli_v2/proxy/runtime.py:16`, `src/cdx_proxy_cli_v2/proxy/management.py:39`, `src/cdx_proxy_cli_v2/proxy/server.py:339`

2. **P1 — `start_service` is a multi-responsibility orchestrator**
   - Reference: `src/cdx_proxy_cli_v2/runtime/service.py:339`

3. **P2 — startup lifecycle should be split into focused helpers**
   - Reference: `src/cdx_proxy_cli_v2/runtime/service.py:339`

## Top Recommendation

Keep this run focused on the lifecycle safety fix; broader refactors stay deferred until behavior-sensitive paths are safer.
