# Scout 05 — Testability

Agent: Bacon (`019cccac-65f7-7000-a43a-6a13f4f4d84c`)
Specialty: testability

## P0
- Existing pytest contract fails after `cdx2` removal.
- Evidence: `pyproject.toml`, `tests/cli/test_main.py`.
- Recommendation: assert `cdx` exists and `cdx2` is absent.

## P1
- No regression test covers the new forced ChatGPT header override behavior.
- Evidence: `src/cdx_proxy_cli_v2/proxy/server.py`, `tests/proxy/test_server.py`.
- Recommendation: add tests for lowercase and conflicting inbound headers on ChatGPT backend requests.

## P2
- No tests guard stale `cdx2` strings that remain in runtime/dashboard surfaces.
- Recommendation: add focused string-contract tests.
