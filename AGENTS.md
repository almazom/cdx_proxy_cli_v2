# cdx_proxy_cli_v2 Agent Notes

## Purpose

Use this file for short repository-local instructions that help agents choose the right verification depth before handoff.

## Required Steps

### E2E Verification

After each major change, run `make test-e2e` from the repository root before handoff.

Treat a change as major when it affects any of these areas:

- auth rotation, cooldown, blacklist, probation, or auto-heal behavior
- proxy request handling or upstream retry behavior
- runtime service lifecycle or background checker behavior
- event logging, traceability, or management endpoints used by E2E flows
- CLI behavior or operator-facing workflows that can change green-path runtime behavior

Command:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
make test-e2e
```

### Full Diagnostics

When you need high confidence that the CLI surface and E2E path are green, run this full diagnostics sequence from the repository root:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

cdx --help
cdx proxy --help
cdx status --help
cdx doctor --help
cdx stop --help
cdx trace --help
cdx logs --help
cdx limits --help
cdx migrate --help
cdx reset --help
cdx rotate --help
cdx all --help
cdx run-server --help

make test-e2e
```

Use the full diagnostics sequence when:

- a major change touched the CLI command surface
- a release or handoff needs extra confidence
- you changed parser wiring, command options, or command help text
- you want confirmation that both command discovery and green-path E2E behavior still work

### When E2E Is Not Required

You usually do not need `make test-e2e` for documentation-only changes or narrow unit-level refactors that do not affect runtime behavior.

### Escalation Rule

If the change touches `bin/codex_wp` or its proxy bootstrap path, prefer running both:

```bash
make test-integration-codex-wp
make test-e2e
```

## Validation

- Treat `make test-e2e` as the slow green-path runtime gate for real end-to-end proxy behavior.
- As of 2026-03-18, `make test-e2e` passes locally with `10 passed`.
- As of 2026-03-18, the full help sweep above exits successfully for all listed `cdx` commands.

## Notes

- Run tests from the repository root so Make targets and relative paths resolve consistently.
- Prefer the full diagnostics sequence over ad hoc spot checks when the change is large enough to affect operator workflows.
- Keep this file short. Put detailed operational procedures in `docs/`.
