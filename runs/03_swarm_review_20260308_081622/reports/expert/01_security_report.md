# Security Scout Report

- Baseline controls are good: loopback-first binding, management-key protection, and token redaction are present.
- Highest-risk gaps are in service lifecycle handling rather than proxy forwarding.

## Findings

1. **P1 — stale-port cleanup can target unrelated local services**
   - References: `src/cdx_proxy_cli_v2/runtime/service.py:231`, `src/cdx_proxy_cli_v2/runtime/service.py:339`, `src/cdx_proxy_cli_v2/runtime/service.py:489`
   - Risk: management key could be sent to an arbitrary listener; unrelated PIDs could be terminated.
   - Fix: verify process identity before sending `/shutdown` or terminating a PID.

2. **P1 — management key leaked in child argv**
   - Reference: `src/cdx_proxy_cli_v2/runtime/service.py:296`
   - Risk: local process listings can expose the key.
   - Fix: keep key in environment only.

3. **P2 — auth symlink containment check is prefix-based**
   - Reference: `src/cdx_proxy_cli_v2/auth/store.py:23`
   - Risk: `/auth2/...` can bypass `/auth` prefix checks.
   - Fix: use canonical path containment.

## Top Recommendation

Implement service lifecycle hardening first; it reduces both secret disclosure and accidental local process termination.
