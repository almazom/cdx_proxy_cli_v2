---
expert_id: "security_sentinel"
expert_name: "Security Sentinel"
run_id: "run_20260216_211732_cdx_proxy_cli_v2"
generated_at_utc: "2026-02-16T21:20:00Z"
read_only_target_repo: true
---

# Executive Summary

- **Top Risk 1**: Access tokens are included in API responses via `collective_health_snapshot` - tokens exposed to any process that can query the dashboard.
- **Top Risk 2**: Management key compared with `hmac.compare_digest` (good) but key generation uses `secrets.token_urlsafe` without explicit length validation.
- **Top Risk 3**: No rate limiting on management endpoints - could be brute-forced for management key.

# P0 (Critical) — Must Fix

## SS-001: Access tokens leaked in collective_health_snapshot response
- **Evidence**: `src/cdx_proxy_cli_v2/health_snapshot.py:74` — `entry["access_token"] = auth.token` includes full token in response. This is later removed at `collective_dashboard.py:260` but `collective_health_snapshot` can be called directly.
- **Impact**: Tokens exposed to any caller of `collective_health_snapshot`, including via `cdx2 all --json` before removal.
- **Recommendation**: Never include tokens in any response payload. Remove line 74 entirely or only include token hash/prefix for identification.
- **Verification**: `rg "access_token.*=.*token" src/` returns no results or only in secure contexts.

## SS-002: Tokens written to event log JSONL files
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:172` — `record_attempt` is called with `auth_name` but not token. However, the event payload could inadvertently include tokens if fields are added. Current implementation is safe but needs explicit documentation.
- **Impact**: Potential future token leakage if event structure changes.
- **Recommendation**: Add explicit token exclusion in `EventLogger.write()`:
  ```python
  SENSITIVE_FIELDS = {"token", "access_token", "password", "secret", "api_key"}
  def write(self, **fields):
      fields = {k: v for k, v in fields.items() if k.lower() not in SENSITIVE_FIELDS}
  ```
- **Verification**: `rg "token\|password\|secret" src/cdx_proxy_cli_v2/observability/event_log.py` shows sanitization.

# P1 (High)

## SS-003: No rate limiting on management endpoint authentication
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:180-187` — `_authorize_management` does constant-time comparison but has no rate limiting or lockout. An attacker could brute-force the management key.
- **Impact**: If management key is weak or leaked, entire proxy is compromised.
- **Recommendation**: Add rate limiting per client IP:
  - Track failed auth attempts per IP
  - Implement exponential backoff
  - Consider using `flask-limiter` pattern or simple in-memory tracker
- **Verification**: `rg "rate.*limit\|brute" src/` finds rate limiting implementation.

## SS-004: Management key stored in plaintext in .env file
- **Evidence**: `src/cdx_proxy_cli_v2/config/settings.py:181-186` — `ensure_management_key` generates and stores key in `.env` file with `chmod 0o600`.
- **Impact**: Any process with file read access can read management key. Key is not encrypted at rest.
- **Recommendation**: While 0o600 permissions are good, consider:
  - Document that management key should be rotated periodically
  - Add `cdx2 rotate-key` command
  - Consider OS keychain integration for key storage
- **Verification**: Security documentation mentions key rotation.

## SS-005: JWT decoding without signature verification
- **Evidence**: `src/cdx_proxy_cli_v2/limits_domain.py:26-38` — `decode_jwt_payload` decodes JWT payload without verifying signature. This is intentional (reading claims, not authenticating) but could be misused.
- **Impact**: If code is copy-pasted for authentication purposes, tokens could be forged.
- **Recommendation**: Add explicit docstring warning:
  ```python
  def decode_jwt_payload(token: str) -> Dict[str, Any]:
      """Decode JWT payload WITHOUT signature verification.
      
      WARNING: This does NOT validate the token signature.
      Only use for extracting claims from trusted tokens.
      Never use for authentication decisions.
      """
  ```
- **Verification**: Docstring includes security warning.

# P2 (Medium)

## SS-006: Shell export escaping may be insufficient
- **Evidence**: `src/cdx_proxy_cli_v2/config/settings.py:195-200` — `format_shell_exports` escapes single quotes but doesn't handle other shell metacharacters like backticks, $(), etc.
- **Impact**: If values contain shell metacharacters, could lead to command injection when eval'd.
- **Recommendation**: Use `shlex.quote()` which handles all shell metacharacters:
  ```python
  def format_shell_exports(values: Dict[str, str]) -> str:
      lines = []
      for key in sorted(values.keys()):
          lines.append(f"export {key}={shlex.quote(values[key])}")
      return "\n".join(lines)
  ```
- **Verification**: `rg "shlex.quote" src/cdx_proxy_cli_v2/config/settings.py` finds usage.

## SS-007: Log files may contain sensitive data
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py:172` — Request paths and headers logged. Paths may contain sensitive tokens or query params.
- **Impact**: Log files may contain sensitive data accessible to anyone with file read access.
- **Recommendation**: Implement log sanitization:
  - Strip Authorization headers from logs
  - Sanitize query parameters that look like tokens
  - Add log retention policy
- **Verification**: `rg "Authorization.*log\|token.*log" src/` confirms no token logging.

## SS-008: No Content-Security-Policy or security headers on responses
- **Evidence**: `src/cdx_proxy_cli_v2/proxy/server.py` — Proxy forwards responses without adding security headers.
- **Impact**: If proxy is exposed (with --allow-non-loopback), responses lack hardening headers.
- **Recommendation**: Add security headers to management endpoint responses:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Cache-Control: no-store` for sensitive endpoints
- **Verification**: Management responses include security headers.

# P3 (Low)

## SS-009: Dependency on `rich` has no version pinning for security
- **Evidence**: `pyproject.toml:26` — `"rich>=13.7,<15"` allows any 13.x or 14.x version. No security advisory tracking.
- **Impact**: Vulnerable versions of rich could be installed.
- **Recommendation**: Add `pip-audit` or `safety` to CI pipeline to check for vulnerable dependencies.
- **Verification**: CI includes dependency security scan.

## SS-010: No security.txt or disclosure policy
- **Evidence**: No `SECURITY.md` or `.well-known/security.txt` in repository.
- **Impact**: Security researchers don't know how to report vulnerabilities.
- **Recommendation**: Add `SECURITY.md` with disclosure policy and contact information.
- **Verification**: `SECURITY.md` exists in project root.

# Notes

- Commands run (read-only):
  - `rg "token\|secret\|password" src/ --type py`
  - `rg "hmac\|compare_digest" src/ --type py`
  - `rg "chmod\|0o600" src/ --type py`
- Assumptions / unknowns:
  - Project assumes localhost-only deployment
  - Management key may be intended to be shared within trusted environment
- Confidence (0-100): 85
