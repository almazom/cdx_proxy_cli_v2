"""Failure classification constants and pool-state enums for the proxy resilience track.

This is a pure data module -- no logic, only constants that are referenced
by server.py, upstream.py, and tests so that every component uses the same
canonical vocabulary when describing *why* something failed and *how bad*
the auth pool currently is.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Failure origins -- the *reason category* attached to observability events.
# ---------------------------------------------------------------------------

FAILURE_ORIGIN_HARD_AUTH: str = "hard_auth"
"""401/403 or a hard auth blacklist reason (token_invalid, forbidden, subscription_expired)."""

FAILURE_ORIGIN_QUOTA: str = "quota"
"""Rate-limit (429) or persistent rate-limit ejection."""

FAILURE_ORIGIN_PROBE_TRANSPORT: str = "probe_transport"
"""Network-level failure during an auto-heal or manual probe (DNS, TCP, TLS)."""

FAILURE_ORIGIN_UPSTREAM_TRANSIENT: str = "upstream_transient"
"""5xx / timeout from the upstream that is *not* auth-related."""

FAILURE_ORIGIN_ACCOUNT_INCOMPATIBLE: str = "account_incompatible"
"""ChatGPT account incompatibility (400 with chatgpt_account_incompatible code)."""

FAILURE_ORIGIN_DOWNSTREAM_DISCONNECT: str = "downstream_disconnect"
"""Client disconnected mid-stream (BrokenPipe, ConnectionReset, etc.)."""

FAILURE_ORIGIN_TIMEOUT: str = "timeout"
"""Request exceeded the configured request_timeout or compact_timeout."""

# ---------------------------------------------------------------------------
# Pool states -- the *health classification* returned by degraded_state_verdict.
# ---------------------------------------------------------------------------

POOL_STATE_HEALTHY: str = "healthy"
"""All auth keys are eligible and no degradation is detected."""

POOL_STATE_DEGRADED: str = "degraded"
"""Some auth keys are unavailable (cooldown), but at least one is still usable."""

POOL_STATE_PARTIAL_OUTAGE: str = "partial_outage"
"""Interactive-safe auths are zero while non-interactive auths may still work."""

POOL_STATE_FULL_OUTAGE: str = "full_outage"
"""No healthy auth keys are available at all."""
