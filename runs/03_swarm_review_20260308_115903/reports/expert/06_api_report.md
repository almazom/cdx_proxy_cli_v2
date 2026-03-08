# Scout 06 — API / UX Contract

Agent: Faraday (`019cccac-7e12-76a2-ac7d-f450c2839d56`)
Specialty: api

## P0
- Public CLI contract still depends on `cdx2` in docs and tests while the package now exposes only `cdx`.
- Evidence: `pyproject.toml`, `README.md`, `docs/operations/runbook.md`, `tests/cli/test_main.py`.
- Recommendation: complete the `cdx`-only rename in one pass.

## P1
- ChatGPT header normalization should be case-insensitive to avoid duplicate casing variants.
- Evidence: `src/cdx_proxy_cli_v2/proxy/server.py`, `src/cdx_proxy_cli_v2/proxy/rules.py`.

- Runtime and dashboard guidance still says `cdx2`.
- Evidence: `src/cdx_proxy_cli_v2/runtime/service.py`, `src/cdx_proxy_cli_v2/observability/all_dashboard.py`.

## P2
- Documentation/help examples are inconsistent and should be swept together.
- Evidence: `README.md`, `docs/operations/runbook.md`, `docs/architecture/overview.md`, `src/cdx_proxy_cli_v2/cli/main.py`.
