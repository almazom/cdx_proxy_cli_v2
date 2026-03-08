# Phase 2 — Scout Consensus Summary

All six scouts converged on two accepted themes and one cleanup recommendation:

1. The repository is in an inconsistent `cdx2` → `cdx` migration state.
   - `pyproject.toml` removed `cdx2`
   - docs and runtime hints still mention `cdx2`
   - tracked pytest contract still requires `cdx2`

2. The ChatGPT header hardening change is directionally correct but incomplete.
   - forcing `Origin`/`Referer`/`User-Agent` is a security/perf win
   - direct case-sensitive assignment can still leave lowercase duplicates
   - no dedicated regression test covers the new path

3. The new untracked wrapper/test files are not the right enforcement mechanism.
   - `scripts/cdx_wrapper.py` is host-specific and masks failures
   - `tests/test_cdx_only.py` is environment-dependent and duplicates tracked coverage

Net result: build cards around finishing the rename atomically, hardening header replacement case-insensitively, and removing scratch artifacts in favor of deterministic pytest coverage.
