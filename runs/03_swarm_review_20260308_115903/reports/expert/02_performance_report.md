# Scout 02 — Performance

Agent: Goodall (`019cccac-30a7-7a00-ae97-6decc61243e7`)
Specialty: performance

## P1
- ChatGPT header override is not case-insensitive, so conflicting lowercase headers can survive and create ambiguous upstream forwarding.
- Evidence: `src/cdx_proxy_cli_v2/proxy/server.py`, `src/cdx_proxy_cli_v2/proxy/rules.py`.
- Recommendation: use `set_header_case_insensitive(...)` for forced `Origin`, `Referer`, and `User-Agent`; add regression tests.

- The branch is red because the tracked CLI contract test still expects `cdx2`.
- Evidence: `pyproject.toml`, `tests/cli/test_main.py`.
- Recommendation: update the contract test to the chosen `cdx`-only behavior.

## P2
- Runtime stale-process guidance still references `cdx2 stop` and slows incident response.
- Evidence: `src/cdx_proxy_cli_v2/runtime/service.py`.
- Recommendation: rename to `cdx stop` and cover with tests.
