# API and UX Scout Report

- Core CLI surface is coherent, but operator-facing mismatches remain.
- The highest-signal issues are command-name drift, reset query encoding, and CLI port validation.

## Findings

1. **P1 — packaged script name does not match documented `cdx2` command**
   - References: `pyproject.toml:30`, `README.md:31`, `src/cdx_proxy_cli_v2/cli/main.py:470`

2. **P1 — `reset` query parameters are not URL-encoded**
   - Reference: `src/cdx_proxy_cli_v2/cli/main.py:363`

3. **P1 — CLI `--port` bypasses range validation**
   - References: `src/cdx_proxy_cli_v2/config/settings.py:157`, `src/cdx_proxy_cli_v2/cli/main.py:574`

## Top Recommendation

Fix the operator contract in one small card: alias `cdx2`, encode reset query params, and fail fast on invalid CLI ports.
