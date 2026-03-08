# Scout 03 — Maintainability

Agent: Euler (`019cccac-4011-7ef1-b6b3-bbc4aaf4b213`)
Specialty: maintainability

## P1
- The CLI contract is internally inconsistent: package entrypoint, docs, runtime guidance, and tests do not agree on `cdx` vs `cdx2`.
- Evidence: `pyproject.toml`, `README.md`, `docs/operations/runbook.md`, `src/cdx_proxy_cli_v2/runtime/service.py`, `tests/cli/test_main.py`.
- Recommendation: choose one contract and update all touched surfaces atomically.

- The proposed `scripts/cdx_wrapper.py` can mask failures and should not be the enforcement layer.
- Evidence: `scripts/cdx_wrapper.py`.
- Recommendation: drop the wrapper and rely on the package entrypoint plus deterministic tests.

## P2
- `src/cdx_proxy_cli_v2/observability/all_dashboard.py` appears stale/unused and still brands output as `cdx2 all`.
- Recommendation: at minimum update strings if retained.
