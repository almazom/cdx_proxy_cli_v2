# Auto-Heal Recovery Runbook

## Purpose

Use this runbook when the auth pool is degraded, review traffic is stalling, or operators need a quick answer about what the proxy is doing and what action to take next.

## Quick Diagnosis

Run these first, in order:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

cdx status
cdx doctor --probe
cdx all
```

What each command gives you:

- `cdx status` shows the top-level health verdict and the one-line pool state guidance.
- `cdx doctor --probe` probes auth keys without mutating runtime state and helps separate bad auths from upstream or transport issues.
- `cdx all` shows quota pressure and per-key dashboard output, which is useful when `429` or `auth.interactive_pool_weak` is involved.

If you need raw management data, check:

```bash
cdx trace --limit 20
curl -sS -H "X-Management-Key: $CLIPROXY_MANAGEMENT_KEY" "$(cdx status --json | jq -r '.base_url')/debug" | jq .
curl -sS -H "X-Management-Key: $CLIPROXY_MANAGEMENT_KEY" "$(cdx status --json | jq -r '.base_url')/health?refresh=1" | jq .
```

## Pool State Decision Tree

### `healthy`

- Meaning: the pool has usable auths and no immediate operator action is needed.
- First action: nothing.
- Follow-up: keep watching `cdx status` and `cdx trace` if the incident is still unfolding.

### `degraded`

- Meaning: some keys are in `COOLDOWN` or `BLACKLIST`, but the pool still has working capacity.
- Try, in order:
  - `cdx rotate`
  - wait for cooldown expiry
  - `cdx reset --state cooldown`
- Confirm recovery with:

```bash
cdx status
cdx doctor --probe
```

### `partial_outage`

- Meaning: the proxy still has auth records, but interactive-safe capacity is gone.
- Typical signals:
  - `auth.interactive_skipped`
  - `auth.interactive_pool_weak`
  - `review.pool_exhausted`
- Try, in order:
  - `cdx doctor --probe`
  - `cdx limits`
  - `cdx reset --state blacklist`

### `full_outage`

- Meaning: no healthy auths remain.
- Try, in order:
  - `cdx reset --state blacklist`
  - add new auth files
  - restart the proxy

Example restart flow:

```bash
cdx stop
cdx proxy
cdx status
```

## Auto-Heal Behavior

Auto-heal runs in the background and periodically probes blacklisted or probation keys. It uses lightweight auth checks and tries to re-enter keys only after repeated success, instead of forcing them back immediately.

Watch these events in `cdx trace`:

- `auto_heal.success`
- `auto_heal.failure`
- `auth.probation`
- `auth.returned`

Important interpretation:

- Repeated `auto_heal.success` means recovery is progressing.
- `auto_heal.failure` means the probe still sees a bad state; check `http_status`, `error_code`, and `origin`.
- The `origin` field helps classify the failure:
  - `hard_auth`
  - `quota`
  - `probe_transport`
  - `upstream_transient`

Useful commands:

```bash
cdx trace --limit 50
cdx doctor --probe
```

## Downstream Disconnects

`proxy.downstream_disconnect` means the upstream side may have been fine, but the client disconnected while the proxy was writing headers, body, or flushing output. This is not the same as an auth failure.

Check these signals:

- trace event: `proxy.downstream_disconnect`
- metric: `downstream_disconnects_total`

Example checks:

```bash
cdx trace --limit 50
curl -sS -H "X-Management-Key: $CLIPROXY_MANAGEMENT_KEY" "$(cdx status --json | jq -r '.base_url')/debug" | jq '.metrics.downstream_disconnects_total'
```

What to do:

- If disconnects rise but auth health is fine, inspect the downstream client or terminal session.
- Do not reset auths only because disconnects are present.

## Review-Path Stall Triage

For review incidents, read the `review.*` lifecycle events in `cdx trace`:

- `review.request_start`
- `review.auth_selected`
- `review.upstream_result`
- `review.pool_exhausted`
- `review.complete`

Suggested reading order:

1. Find `review.request_start`.
2. Check whether `review.auth_selected` happened.
3. Check every `review.upstream_result`.
4. Look for `review.pool_exhausted`.
5. Confirm whether `review.complete` happened.

Interpretation:

- `review.request_start` without `review.auth_selected` usually points to pool gating before upstream traffic.
- `review.auth_selected` without a later success often means retry pressure, upstream failure, or review-path exhaustion.
- `review.pool_exhausted` means interactive-safe auths were not available or safe retries were exhausted.

Related events to watch beside `review.*`:

- `auth.interactive_skipped`
- `auth.interactive_pool_weak`

## Operator Checklist

- Start with `cdx status`, `cdx doctor --probe`, and `cdx all`.
- Use `/debug` or `cdx status --json` to read the triage summary quickly.
- Use `cdx trace` when you need exact event ordering.
- Use `cdx limits` when quota pressure is suspected.
- Reset only the state you understand: `cooldown`, `blacklist`, or `probation`.
