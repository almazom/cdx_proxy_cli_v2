# TaaD Report Template (AI-Generated Code Gate)

Use this report as the final acceptance gate for AI-generated changes.

## Metadata

- Report ID:
- Date (YYYY-MM-DD):
- Reviewer:
- Agent:
- Task:
- Branch/Commit:

## 1. Status

Choose exactly one:

- [ ] `APPROVED`
- [ ] `APPROVED_WITH_NOTES`
- [ ] `REJECTED`

## 2. Summary

- What was implemented:
- Does it match the request:
- Code quality snapshot:

## 3. Discrepancies

| Type | Description | Severity | File/Reference |
|------|-------------|----------|----------------|
| Bug / Style / Performance / Security / Docs | | High / Medium / Low | |

## 4. Impact Analysis

- What breaks if left unchanged:
- Side effects:
- Edge cases covered:
- Backward compatibility impact:

## 5. Verification Evidence

Record commands and outcomes:

```bash
python3 -m pytest -q
PYTHONPATH=src python3 -m cdx_proxy_cli_v2 --help
```

- Tests result:
- Runtime smoke result:
- Notes:

## 6. Decision Notes

- Required follow-ups (if any):
- Suggested improvements (non-blocking):

## 7. Sign-off

- Reviewed by:
- Date:
- Final comment:
