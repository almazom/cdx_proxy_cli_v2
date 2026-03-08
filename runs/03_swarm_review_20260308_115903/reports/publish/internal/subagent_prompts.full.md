# Internal Exact Prompt Registry

## Scout — Bohr — security
You are Scout 1 (security) for swarm_review flow v6.5.3 on repo `/home/pets/TOOLS/cdx_proxy_cli_v2`. Focus on the live migration from `cdx2` to `cdx` and any security impact in current uncommitted changes. Inspect relevant files in `src/`, `tests/`, `README.md`, `docs/`, `pyproject.toml`, and the current git diff. Return a concise markdown report with: 1) top findings prioritized P0/P1/P2, 2) exact file:line evidence, 3) recommended fixes, 4) whether current diff introduces any regressions or security wins. Do not modify files.

### Follow-up gate prompts used later
- Phase 0 preflight review prompt
- Phase 3 fusion review prompt
- Phase 5 quality gate prompt
- Phase 8 implementation gate prompt
- Phase 9 final gate prompt

## Scout — Goodall — performance
You are Scout 2 (performance) for swarm_review flow v6.5.3 on repo `/home/pets/TOOLS/cdx_proxy_cli_v2`. Focus on the live migration from `cdx2` to `cdx` and the proxy header change in `src/cdx_proxy_cli_v2/proxy/server.py`. Inspect current git diff plus nearby code/tests. Return a concise markdown report with prioritized P0/P1/P2 findings, exact file:line evidence, impact, and recommended fixes. Do not modify files.

## Scout — Euler — maintainability
You are Scout 3 (maintainability) for swarm_review flow v6.5.3 on repo `/home/pets/TOOLS/cdx_proxy_cli_v2`. Review the live diff and surrounding modules for consistency, leftover `cdx2` references, contract drift, and risky duplication. Inspect `src/`, `tests/`, `README.md`, `docs/`, `pyproject.toml`, and any untracked files tied to this change. Return a concise markdown report with P0/P1/P2 findings, exact file:line evidence, and concrete fixes. Do not modify files.

## Scout — Locke — simplicity
You are Scout 4 (simplicity) for swarm_review flow v6.5.3 on repo `/home/pets/TOOLS/cdx_proxy_cli_v2`. Review the live diff, especially whether the proposed `scripts/cdx_wrapper.py` and `tests/test_cdx_only.py` are the simplest stable way to enforce the `cdx`-only contract. Look for unnecessary complexity, redundant files, and clearer alternatives. Return a concise markdown report with P0/P1/P2 findings, exact file:line evidence, and recommended simplifications. Do not modify files.

## Scout — Bacon — testability
You are Scout 5 (testability) for swarm_review flow v6.5.3 on repo `/home/pets/TOOLS/cdx_proxy_cli_v2`. Focus on tests around the `cdx2`→`cdx` migration and the proxy header override behavior. Inspect current git diff plus relevant pytest files. Return a concise markdown report with prioritized findings, exact file:line evidence, missing regression coverage, flaky/environment-dependent tests if any, and recommended fixes. Do not modify files.

## Scout — Faraday — api
You are Scout 6 (api/ux contract) for swarm_review flow v6.5.3 on repo `/home/pets/TOOLS/cdx_proxy_cli_v2`. Review user-facing CLI/API contract drift caused by the active changes: command names, help text, docs, runtime messages, and header normalization for ChatGPT upstream requests. Return a concise markdown report with P0/P1/P2 findings, exact file:line evidence, and concrete fixes. Do not modify files.

## Worker — Descartes — CARD-001
You are Worker 1 for swarm_review run `03_swarm_review_20260308_115903` in `/home/pets/TOOLS/cdx_proxy_cli_v2`. You are not alone in the codebase; do not revert others' edits, and adjust to concurrent changes if needed. You own ONLY these files: `pyproject.toml`, `tests/cli/test_main.py`, `README.md`, `docs/operations/runbook.md`, `docs/architecture/overview.md`, `src/cdx_proxy_cli_v2/runtime/service.py`, `src/cdx_proxy_cli_v2/observability/all_dashboard.py`, `proxy_debug_report.html`, and deletion of `scripts/cdx_wrapper.py` plus `tests/test_cdx_only.py`. Implement CARD-001 from `runs/03_swarm_review_20260308_115903/cards/CARD-001.md`: finish the `cdx`-only contract atomically, remove scratch wrapper/test artifacts, and keep tests deterministic. After edits, run focused validation for your scope if possible and report: summary, changed_files, validation_run, risks.

## Worker — Pasteur — CARD-002
You are Worker 2 for swarm_review run `03_swarm_review_20260308_115903` in `/home/pets/TOOLS/cdx_proxy_cli_v2`. You are not alone in the codebase; do not revert others' edits, and adjust to concurrent changes if needed. You own ONLY these files: `src/cdx_proxy_cli_v2/proxy/server.py` and `tests/proxy/test_server.py`. Implement CARD-002 from `runs/03_swarm_review_20260308_115903/cards/CARD-002.md`: make forced ChatGPT header replacement case-insensitive and add regression tests for conflicting/lowercase headers while leaving non-ChatGPT behavior unchanged. After edits, run focused validation for your scope if possible and report: summary, changed_files, validation_run, risks.
