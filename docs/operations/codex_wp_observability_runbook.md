# codex_wp Observability Runbook

## Purpose

Use this runbook during a live `codex_wp` session when the operator needs to tell whether the stall happened before proxy traffic, during review-path auth selection, during upstream attempts, or after the proxy already succeeded.

## Live Trace During a codex_wp Session

Start with the runtime surfaces that give the fastest answer:

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

cdx status --json
cdx trace --limit 20
cdx doctor --probe
```

If you need a live incident loop, keep one terminal on:

```bash
watch -n 5 'cdx status'
```

And another on:

```bash
cdx trace --limit 50
```

For management snapshots, use:

```bash
BASE_URL="$(cdx status --json | jq -r '.base_url')"
curl -sS -H "X-Management-Key: $CLIPROXY_MANAGEMENT_KEY" "$BASE_URL/debug" | jq .
curl -sS -H "X-Management-Key: $CLIPROXY_MANAGEMENT_KEY" "$BASE_URL/trace?limit=50" | jq .
```

## Events to Watch

These are the main events for `codex_wp` incident triage:

- `auth.interactive_skipped`
- `auth.interactive_pool_weak`
- `proxy.downstream_disconnect`
- `review.request_start`
- `review.auth_selected`
- `review.upstream_result`
- `review.pool_exhausted`
- `review.complete`

How to read them:

- `auth.interactive_skipped`: some auths exist, but they were filtered out as unsafe for interactive routes.
- `auth.interactive_pool_weak`: no interactive-safe auths were available for the request path.
- `proxy.downstream_disconnect`: the client side dropped while the proxy was writing output.
- `review.request_start`: request entered the review path.
- `review.auth_selected`: an auth was chosen for an attempt.
- `review.upstream_result`: one upstream attempt completed; inspect `status`, `error_code`, and `latency_ms`.
- `review.pool_exhausted`: safe auths were unavailable or safe retries were exhausted.
- `review.complete`: final result was delivered by the proxy path.

## Quota Pressure Diagnosis

When the incident looks like usage pressure rather than token breakage, use:

```bash
cdx limits
cdx all
cdx doctor --probe
```

What to look for:

- high usage windows in `cdx limits`
- many keys in `COOLDOWN`
- `429` in `review.upstream_result`
- `auth.interactive_pool_weak` with few or zero interactive-safe auths

Useful pattern:

```bash
cdx status --json | jq '.triage_summary'
cdx limits --json
cdx all --json
```

## Interactive Usage-Limit Banner

The interactive usage-limit banner usually means the request path is still alive, but the review flow cannot find safe capacity for interactive traffic.

Check first:

1. `cdx status`
2. `cdx doctor --probe`
3. `cdx limits`
4. `cdx trace --limit 50`

If you see `auth.interactive_pool_weak` or `review.pool_exhausted`:

- confirm whether keys are limited or blacklisted
- decide whether the issue is quota pressure, hard auth failure, or temporary cooldown
- use `cdx reset --state blacklist` only when blacklist state is the real blocker

## Fast Triage Mapping

### No `review.request_start`

- likely outside the proxy path
- inspect `codex_wp` launcher, shell, or child process lifecycle

### `review.request_start` but no `review.auth_selected`

- likely blocked by interactive-safe auth gating
- check `auth.interactive_skipped` and `auth.interactive_pool_weak`

### `review.auth_selected` plus repeated `review.upstream_result`

- the proxy is working, but retries or quota pressure are active
- inspect `status`, `error_code`, and `latency_ms`

### `review.complete` followed by user-visible hang

- proxy path likely succeeded
- inspect child exit handling and downstream client behavior
- check `proxy.downstream_disconnect`

## Recommended Incident Bundle

Capture these when escalating:

```bash
cdx status --json
cdx doctor --json --probe
cdx limits --json
cdx all --json
cdx trace --limit 50
```

Include:

- the current `triage_summary`
- the exact `review.*` sequence
- any `auth.interactive_skipped` or `auth.interactive_pool_weak` events
- any `proxy.downstream_disconnect` events
