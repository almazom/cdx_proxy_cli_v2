# Phase 3 — Fusion Report

## Inputs
- `reports/expert/01_security_report.md`
- `reports/expert/02_performance_report.md`
- `reports/expert/03_maintainability_report.md`
- `reports/expert/04_simplicity_report.md`
- `reports/expert/05_testability_report.md`
- `reports/expert/06_api_report.md`

## Consensus

### P0 — Finish the `cdx`-only contract atomically
All castes agreed the branch is currently inconsistent:
- `pyproject.toml` removed `cdx2`
- `tests/cli/test_main.py` still requires `cdx2`
- `README.md`, `docs/operations/runbook.md`, runtime warnings, and dashboard titles still mention `cdx2`
- the new `scripts/cdx_wrapper.py` and `tests/test_cdx_only.py` are not a stable way to enforce the contract

### P1 — Complete the ChatGPT header hardening
Security, performance, and testability agreed the direction is correct but the implementation is incomplete:
- direct assignment in `proxy/server.py` is case-sensitive
- lowercase inbound headers can coexist with canonical header names
- no direct regression test locks the intended behavior

## Accepted Findings
1. `cli.cdx_contract_drift` → accepted as a card
2. `proxy.chatgpt_header_casefold_override` → accepted as a card

## Rejected / Deferred
- `security.eval_path_ambiguity` → deferred for a future contract decision; not a blocker for the current migration completion
- `maintainability.all_dashboard_deeper_cleanup` → deferred; only public string alignment is needed now

## Outcome
Proceed to card design with two implementation cards and explicit deferred findings.
