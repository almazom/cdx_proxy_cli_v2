# TaaD Checklist (Quick Pass/Fail)

Run this checklist before accepting AI-generated code.

## Functional Fit

- [ ] Change solves the requested task.
- [ ] No missing requirements from the prompt.
- [ ] CLI behavior/output remains consistent where expected.

## Safety and Reliability

- [ ] No obvious runtime crashes on normal path.
- [ ] Errors are handled (clear messages, no silent failures).
- [ ] No sensitive data leaks in logs or output.

## Code Quality

- [ ] Module boundaries remain clean and readable.
- [ ] Imports are valid (no invented packages).
- [ ] New code follows repository style and naming.
- [ ] Complex logic has concise comments where needed.

## Regression Guard

- [ ] Existing tests pass.
- [ ] New/changed behavior has test coverage when needed.
- [ ] No unrelated files were modified accidentally.

## Verification Commands

```bash
python3 -m pytest -q
PYTHONPATH=src python3 -m cdx_proxy_cli_v2 --help
```

## Decision

- [ ] Accept (`APPROVED`)
- [ ] Accept with notes (`APPROVED_WITH_NOTES`)
- [ ] Reject (`REJECTED`)

## Notes

- Blocking issues:
- Non-blocking issues:
