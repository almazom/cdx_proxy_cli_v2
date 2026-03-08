# Scout 01 — Security

Agent: Bohr (`019cccac-1bd5-7343-acfa-aa486fd9dbee`)
Specialty: security

## P1
- `cdx`-only migration increases ambiguity in `eval "$(cdx ... --print-env-only)"` guidance because the generic executable name can collide on `PATH`.
- Evidence: `src/cdx_proxy_cli_v2/cli/main.py`, `pyproject.toml`.
- Recommendation: keep the user-facing contract consistent and, if needed later, revisit whether the eval hint should resolve the executable path explicitly.

## P2
- ChatGPT header hardening improved, but direct case-sensitive assignment can leave lowercase duplicates like `origin` alongside `Origin`.
- Evidence: `src/cdx_proxy_cli_v2/proxy/server.py`, `src/cdx_proxy_cli_v2/proxy/rules.py`.
- Recommendation: use case-insensitive replacement helpers and add regression coverage.

- Migration remains inconsistent across docs/runtime/tests and can mislead operators toward stale commands.
- Evidence: `README.md`, `docs/operations/runbook.md`, `src/cdx_proxy_cli_v2/runtime/service.py`, `tests/cli/test_main.py`.
- Recommendation: finish the rename atomically.
