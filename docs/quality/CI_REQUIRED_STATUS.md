# Required CI Status for TaaD

To enforce TaaD as a merge gate, configure branch protection and require this
job to pass:

- Workflow file: `.github/workflows/ci.yml`
- Required status check: `TaaD Quality Gate`

Recommended policy:

1. Protect `main` branch.
2. Require pull request before merge.
3. Require status checks and select `TaaD Quality Gate`.
4. Optionally also require `Regression Tests`.
