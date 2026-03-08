# Public Prompt Registry (Redacted)

All prompts below are sanitized summaries. Exact absolute paths and internal orchestration details are preserved only in `internal/subagent_prompts.full.md` and are not publish targets.

- **Bohr / security scout** — audited the `cdx2`→`cdx` migration for security regressions and wins.
- **Goodall / performance scout** — reviewed the header change path and performance risks around duplicate forwarded headers.
- **Euler / maintainability scout** — checked contract consistency, drift, and risky duplication.
- **Locke / simplicity scout** — evaluated whether scratch wrapper/tests were necessary or redundant.
- **Bacon / testability scout** — reviewed regression coverage, flaky/environment-coupled tests, and missing assertions.
- **Faraday / API scout** — reviewed user-facing CLI/API contract drift and documentation consistency.
- **Descartes / worker** — completed the `cdx`-only contract migration and removed scratch artifacts.
- **Pasteur / worker** — hardened ChatGPT header replacement and added `_proxy_request` regressions.

Repeated gate-review prompts asked reviewers to judge preflight, fusion, quality, implementation, and final readiness using only the corresponding phase artifacts.
