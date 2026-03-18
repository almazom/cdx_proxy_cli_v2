# Codex Exec + Proxy Integration

**Last verified:** 2026-03-18
**Status:** OK

## Purpose

`codex exec` works through the local proxy when the shell is initialized via
`cdx proxy --print-env-only`, which now wraps `codex` with
`-c openai_base_url=...` for current Codex CLI builds.

## Preconditions

- `cdx` is installed and can start or reuse the local proxy service.
- `codex` CLI is installed in the current shell.
- The shell is initialized with `eval "$(cdx proxy --print-env-only)"`, or the repo helper `bin/codex_wp` is used for a one-shot command.

## Required Steps

```bash
cdx proxy
eval "$(cdx proxy --print-env-only)"
codex exec --json --ephemeral --skip-git-repo-check -C /tmp 'Reply with the single word OK and stop.'
```

Equivalent one-shot wrapper check:

```bash
bin/codex_wp exec --json --ephemeral --skip-git-repo-check -C /tmp 'Reply with the single word OK and stop.'
```

## Validation

Verified locally on 2026-03-18:

- `codex exec --json --ephemeral --skip-git-repo-check -C /tmp 'Reply with the single word OK and stop.'`
- proxy base URL: `http://127.0.0.1:52679`
- result: final agent message `OK`
- proxy event log recorded new proxied traffic during the run

Observed proxy traffic for a successful run includes:

- `GET /models?client_version=...` with `200`
- `POST /responses` with `200`

That means the earlier "models endpoint bypasses proxy" note is no longer accurate for the
currently tested Codex CLI build.

Recommended follow-up checks:

```bash
cdx status --json
tail -n 20 ~/.codex/_auths/rr_proxy_v2.events.jsonl
```

## Notes

- `bin/codex_wp` performs the same proxy bootstrap for a single `codex` invocation and injects `openai_base_url` explicitly.
- For a reproducible multi-step smoke test with trace and event-log evidence, use `docs/operations/codex_wp_observability_runbook.md`.
- Websocket auth failures should now rotate to the next key instead of leaving the bad key in service.
- Non-auth client errors such as `405 Method Not Allowed` should not poison a healthy key.
