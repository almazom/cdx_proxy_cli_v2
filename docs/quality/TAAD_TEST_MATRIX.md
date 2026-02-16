# TaaD Test Matrix (Tests = Documentation)

This matrix links TaaD principles to executable tests.

## Functional Fit

- `tests/taad/test_taad_auth_contracts.py::test_taad_auth_store_accepts_supported_token_shapes`
- `tests/taad/test_taad_traceability_contracts.py::test_taad_retry_flow_is_traceable_with_single_request_id`

## Safety and Reliability

- `tests/taad/test_taad_auth_contracts.py::test_taad_auth_store_ignores_invalid_or_empty_token_files`
- `tests/taad/test_taad_management_contracts.py::test_taad_management_endpoints_require_management_key`
- `tests/taad/test_taad_management_contracts.py::test_taad_health_endpoint_is_operationally_readable`

## Traceability and Operability

- `tests/taad/test_taad_traceability_contracts.py::test_taad_retry_flow_is_traceable_with_single_request_id`

## Run

```bash
python3 -m pytest -q tests/taad
```

## Acceptance Rule

- `APPROVED`: all TaaD tests pass.
- `APPROVED_WITH_NOTES`: tests pass, non-blocking notes exist.
- `REJECTED`: any TaaD test fails or critical flow is unverified.
