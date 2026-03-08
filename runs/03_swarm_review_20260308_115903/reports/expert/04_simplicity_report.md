# Scout 04 — Simplicity

Agent: Locke (`019cccac-5210-7a01-8b99-609b31595dcc`)
Specialty: simplicity

## P0
- Current diff breaks the tracked CLI contract test because `cdx2` was removed from `pyproject.toml` while existing tests still require it.
- Evidence: `pyproject.toml`, `tests/cli/test_main.py`.
- Recommendation: update the existing test to the `cdx`-only contract instead of introducing a separate environment-heavy suite.

## P1
- `scripts/cdx_wrapper.py` is host-specific, side-effectful, and does not propagate failures correctly.
- `tests/test_cdx_only.py` is environment-coupled and redundant for this migration.
- Recommendation: remove both and keep coverage in the existing pytest suite.

- `cdx2` rename remains incomplete in runtime strings and dashboard titles.
- Evidence: `src/cdx_proxy_cli_v2/runtime/service.py`, `src/cdx_proxy_cli_v2/observability/all_dashboard.py`.
