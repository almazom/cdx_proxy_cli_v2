# TaaD Test Suite: Tests As Documentation

This folder is a behavior contract for AI-generated changes.
Each test is written as an executable requirement and maps to a TaaD gate.

## Coverage Map

- `test_taad_auth_contracts.py`
  - accepted auth formats
  - invalid/tokens-missing files are safely ignored
- `test_taad_management_contracts.py`
  - management endpoints are protected by key
  - health endpoint exposes stable shape for operators
- `test_taad_traceability_contracts.py`
  - retry path is traceable (`request_id`, `attempt`, auth switch)
  - cooldown policy triggers key rotation on `401`
- `test_taad_rotation_policy_contracts.py`
  - `401/403` drives temporary blacklist ejection
  - blacklisted keys return only through probation (controlled re-entry)
  - `429` moves key into cooldown and rotation continues

## How to Run

```bash
python3 -m pytest -q tests/taad
```

## Why this matters

TaaD is the final acceptance gate for AI-generated code:

- functional fit
- runtime safety
- traceability for debugging
- regression confidence
