# Codex Exec + Proxy Integration

**Last verified:** 2026-03-11  
**Status:** OK

## Current behavior

`codex exec` works through the local proxy when `OPENAI_BASE_URL` / `OPENAI_API_BASE`
point at a running `cdx proxy` instance.

Verified locally on 2026-03-11:

- `codex exec --json --ephemeral --skip-git-repo-check -C /tmp 'Reply with the single word OK and stop.'`
- proxy base URL: `http://127.0.0.1:42209`
- result: final agent message `OK`
- proxy event log recorded new proxied traffic during the run

Observed proxy traffic for a successful run includes:

- `GET /responses` with `101` websocket upgrade
- `GET /models?client_version=...` with `200`

That means the earlier "models endpoint bypasses proxy" note is no longer accurate for the
currently tested Codex CLI build.

## Quick check

```bash
cdx proxy
eval "$(cdx proxy --print-env-only)"
codex exec --json --ephemeral --skip-git-repo-check -C /tmp 'Reply with the single word OK and stop.'
```

Then inspect:

```bash
cdx doctor --probe --json
tail -n 20 ~/.codex/_auths/rr_proxy_v2.events.jsonl
```

## Notes

- Websocket auth failures should now rotate to the next key instead of leaving the bad key in service.
- Non-auth client errors such as `405 Method Not Allowed` should not poison a healthy key.
