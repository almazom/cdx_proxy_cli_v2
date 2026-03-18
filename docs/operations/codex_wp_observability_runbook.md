# codex_wp Multi-Step Observability Runbook

**Last verified:** 2026-03-18
**Status:** PASS

## Purpose

Use this runbook to test `bin/codex_wp` with a deterministic multi-step prompt and collect enough evidence to answer three questions:

1. Did `codex_wp` complete successfully?
2. Did the request flow through the proxy?
3. Can the run be traced afterward with stable artifacts and request metadata?

## Inputs

- repository root: `/home/pets/TOOLS/cdx_proxy_cli_v2`
- auth dir: `~/.codex/_auths` unless you intentionally use another one
- tools: `cdx`, `codex`, `curl`, `jq`, `tee`

## Preconditions

- `cdx status --json --auth-dir ~/.codex/_auths` reports `"healthy": true`, or `cdx proxy --auth-dir ~/.codex/_auths` can start the service
- `bin/codex_wp` exists and is executable
- the auth dir `.env` contains `CLIPROXY_MANAGEMENT_KEY`
- you can write temporary artifacts under `/tmp`

## Required Steps

### 1. Prepare an artifact directory and runtime variables

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

export AUTH_DIR="${AUTH_DIR:-$HOME/.codex/_auths}"
export ARTIFACT_DIR="/tmp/codex_wp_observe_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ARTIFACT_DIR"

cdx proxy --auth-dir "$AUTH_DIR"

export BASE_URL="$(cdx status --json --auth-dir "$AUTH_DIR" | jq -r '.base_url')"
export EVENTS_FILE="$(cdx status --json --auth-dir "$AUTH_DIR" | jq -r '.events_file')"
export LOG_FILE="$(cdx status --json --auth-dir "$AUTH_DIR" | jq -r '.log_file')"
export MGMT_KEY="$(sed -n 's/^CLIPROXY_MANAGEMENT_KEY=//p' "$AUTH_DIR/.env" | tail -n 1)"
```

### 2. Capture the baseline before the `codex_wp` run

```bash
cdx status --json --auth-dir "$AUTH_DIR" | tee "$ARTIFACT_DIR/status.before.json"
cdx doctor --json --auth-dir "$AUTH_DIR" | tee "$ARTIFACT_DIR/doctor.before.json"
curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq . | tee "$ARTIFACT_DIR/debug.before.json"
jq -r '.metrics.requests_total' "$ARTIFACT_DIR/debug.before.json" | tee "$ARTIFACT_DIR/requests_total.before"
curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/health?refresh=1" | jq . | tee "$ARTIFACT_DIR/health.before.json"
curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/trace?limit=20" | jq . | tee "$ARTIFACT_DIR/trace.before.json"
wc -l < "$EVENTS_FILE" | tee "$ARTIFACT_DIR/events.before.count"
```

Optional live view in another terminal:

```bash
cdx trace --auth-dir "$AUTH_DIR" --limit 20
```

### 3. Run request 1 and collect proof that it went through the proxy

```bash
REQ1_EVENTS_BEFORE="$(wc -l < "$EVENTS_FILE")"
REQ1_REQUESTS_BEFORE="$(curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq -r '.metrics.requests_total')"

bin/codex_wp exec --json --ephemeral --skip-git-repo-check -C /tmp \
  'Reply with exactly REQ1 OK and stop.' \
  | tee "$ARTIFACT_DIR/request1.jsonl"

jq -rs '
  [
    .[]
    | select(.type == "item.completed")
    | select(.item.type == "agent_message")
    | .item.text
  ]
  | last
' "$ARTIFACT_DIR/request1.jsonl" | tee "$ARTIFACT_DIR/request1.final.txt"

REQ1_EVENTS_AFTER="$(wc -l < "$EVENTS_FILE")"
REQ1_REQUESTS_AFTER="$(curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq -r '.metrics.requests_total')"

printf '%s\n' "$((REQ1_EVENTS_AFTER - REQ1_EVENTS_BEFORE))" | tee "$ARTIFACT_DIR/request1.events.delta"
printf '%s\n' "$((REQ1_REQUESTS_AFTER - REQ1_REQUESTS_BEFORE))" | tee "$ARTIFACT_DIR/request1.requests.delta"

sed -n "$((REQ1_EVENTS_BEFORE + 1)),$((REQ1_EVENTS_AFTER))p" "$EVENTS_FILE" \
  | tee "$ARTIFACT_DIR/request1.events.delta.jsonl"

jq -rs '
  [
    .[]
    | select(.event == "proxy.request")
    | {request_id, attempt, method, path, status, auth_file}
  ]
' "$ARTIFACT_DIR/request1.events.delta.jsonl" | tee "$ARTIFACT_DIR/request1.proxy.json"
```

Expected request-1 result:

```text
REQ1 OK
```

### 4. Run request 2 as a real multi-step task and collect proxy proof

```bash
REQ2_EVENTS_BEFORE="$(wc -l < "$EVENTS_FILE")"
REQ2_REQUESTS_BEFORE="$(curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq -r '.metrics.requests_total')"

PROMPT=$'Work only in the current directory.\n1. Create a file named proof.txt containing exactly alpha-beta.\n2. Read proof.txt.\n3. Reply with exactly three lines:\nSTEP1 OK\nSTEP2 OK\nFILE=alpha-beta'

bin/codex_wp exec --json --ephemeral --skip-git-repo-check -C /tmp "$PROMPT" \
  | tee "$ARTIFACT_DIR/request2.jsonl"

jq -rs '
  [
    .[]
    | select(.type == "item.completed")
    | select(.item.type == "agent_message")
    | .item.text
  ]
  | last
' "$ARTIFACT_DIR/request2.jsonl" | tee "$ARTIFACT_DIR/request2.final.txt"

REQ2_EVENTS_AFTER="$(wc -l < "$EVENTS_FILE")"
REQ2_REQUESTS_AFTER="$(curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq -r '.metrics.requests_total')"

printf '%s\n' "$((REQ2_EVENTS_AFTER - REQ2_EVENTS_BEFORE))" | tee "$ARTIFACT_DIR/request2.events.delta"
printf '%s\n' "$((REQ2_REQUESTS_AFTER - REQ2_REQUESTS_BEFORE))" | tee "$ARTIFACT_DIR/request2.requests.delta"

sed -n "$((REQ2_EVENTS_BEFORE + 1)),$((REQ2_EVENTS_AFTER))p" "$EVENTS_FILE" \
  | tee "$ARTIFACT_DIR/request2.events.delta.jsonl"

jq -rs '
  [
    .[]
    | select(.event == "proxy.request")
    | {request_id, attempt, method, path, status, auth_file}
  ]
' "$ARTIFACT_DIR/request2.events.delta.jsonl" | tee "$ARTIFACT_DIR/request2.proxy.json"
```

Expected request-2 result:

```text
STEP1 OK
STEP2 OK
FILE=alpha-beta
```

### 5. Run request 3 and collect proxy proof

```bash
REQ3_EVENTS_BEFORE="$(wc -l < "$EVENTS_FILE")"
REQ3_REQUESTS_BEFORE="$(curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq -r '.metrics.requests_total')"

bin/codex_wp exec --json --ephemeral --skip-git-repo-check -C /tmp \
  'Reply with exactly PROXY CHECK OK and stop.' \
  | tee "$ARTIFACT_DIR/request3.jsonl"

jq -rs '
  [
    .[]
    | select(.type == "item.completed")
    | select(.item.type == "agent_message")
    | .item.text
  ]
  | last
' "$ARTIFACT_DIR/request3.jsonl" | tee "$ARTIFACT_DIR/request3.final.txt"

REQ3_EVENTS_AFTER="$(wc -l < "$EVENTS_FILE")"
REQ3_REQUESTS_AFTER="$(curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq -r '.metrics.requests_total')"

printf '%s\n' "$((REQ3_EVENTS_AFTER - REQ3_EVENTS_BEFORE))" | tee "$ARTIFACT_DIR/request3.events.delta"
printf '%s\n' "$((REQ3_REQUESTS_AFTER - REQ3_REQUESTS_BEFORE))" | tee "$ARTIFACT_DIR/request3.requests.delta"

sed -n "$((REQ3_EVENTS_BEFORE + 1)),$((REQ3_EVENTS_AFTER))p" "$EVENTS_FILE" \
  | tee "$ARTIFACT_DIR/request3.events.delta.jsonl"

jq -rs '
  [
    .[]
    | select(.event == "proxy.request")
    | {request_id, attempt, method, path, status, auth_file}
  ]
' "$ARTIFACT_DIR/request3.events.delta.jsonl" | tee "$ARTIFACT_DIR/request3.proxy.json"
```

Expected request-3 result:

```text
PROXY CHECK OK
```

### 6. Capture the state after the three-request run

```bash
cdx status --json --auth-dir "$AUTH_DIR" | tee "$ARTIFACT_DIR/status.after.json"
cdx doctor --json --auth-dir "$AUTH_DIR" | tee "$ARTIFACT_DIR/doctor.after.json"
curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/debug" | jq . | tee "$ARTIFACT_DIR/debug.after.json"
jq -r '.metrics.requests_total' "$ARTIFACT_DIR/debug.after.json" | tee "$ARTIFACT_DIR/requests_total.after"
curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/health?refresh=1" | jq . | tee "$ARTIFACT_DIR/health.after.json"
curl -sS -H "X-Management-Key: $MGMT_KEY" "$BASE_URL/trace?limit=50" | jq . | tee "$ARTIFACT_DIR/trace.after.json"
wc -l < "$EVENTS_FILE" | tee "$ARTIFACT_DIR/events.after.count"
tail -n 80 "$EVENTS_FILE" | tee "$ARTIFACT_DIR/events.after.tail.jsonl"
tail -n 80 "$LOG_FILE" | tee "$ARTIFACT_DIR/log.after.tail.txt"
```

### 7. Confirm that all three requests advanced proxy-visible counters

```bash
printf '%s\n' "$(( $(cat "$ARTIFACT_DIR/requests_total.after") - $(cat "$ARTIFACT_DIR/requests_total.before") ))" \
  | tee "$ARTIFACT_DIR/requests_total.delta"

printf '%s\n' "$(( $(cat "$ARTIFACT_DIR/events.after.count") - $(cat "$ARTIFACT_DIR/events.before.count") ))" \
  | tee "$ARTIFACT_DIR/events_total.delta"
```

Expected result:

```text
3
3
```

Interpretation:

- first line: total proxy request growth seen by `/debug`
- second line: total new event-log lines appended during the three-request sequence

### 8. Review the final messages from all three requests

```bash
cat "$ARTIFACT_DIR/request1.final.txt"
printf '\n'
cat "$ARTIFACT_DIR/request2.final.txt"
printf '\n'
cat "$ARTIFACT_DIR/request3.final.txt"
printf '\n'
```

### 9. Correlate proxy trace and event-log evidence

Show recent proxied requests from the management trace snapshot:

```bash
jq -r '
  .events[]
  | select(.event == "proxy.request")
  | [.request_id, .attempt, .method, .path, .status, .auth_file]
  | @tsv
' "$ARTIFACT_DIR/trace.after.json" | tee "$ARTIFACT_DIR/trace.requests.tsv"
```

Show the proxy events captured specifically during each numbered request:

```bash
jq -r '.[] | [.request_id, .attempt, .method, .path, .status, .auth_file] | @tsv' "$ARTIFACT_DIR/request1.proxy.json"
jq -r '.[] | [.request_id, .attempt, .method, .path, .status, .auth_file] | @tsv' "$ARTIFACT_DIR/request2.proxy.json"
jq -r '.[] | [.request_id, .attempt, .method, .path, .status, .auth_file] | @tsv' "$ARTIFACT_DIR/request3.proxy.json"
```

Show recent persisted request events from the full event-log tail:

```bash
jq -r '
  select(.event == "proxy.request")
  | [.request_id, .attempt, .method, .path, .status, .auth_file]
  | @tsv
' "$ARTIFACT_DIR/events.after.tail.jsonl" | tee "$ARTIFACT_DIR/event-log.requests.tsv"
```

Current Codex CLI builds may confirm proxy usage with websocket upgrade traffic such as `GET /responses` with status `101`. That still counts as valid proxy proof when the event came from the per-request delta files and `/debug` request totals also increased.

### 10. Review auth-pool state after the run

```bash
jq '.summary' "$ARTIFACT_DIR/doctor.before.json"
jq '.summary' "$ARTIFACT_DIR/doctor.after.json"
```

For a normal successful smoke run, you want the proxy to remain healthy and the auth summary to avoid unexpected state regression compared with the baseline.

## Green Path Expectations

Use the run as a healthy baseline when the following signals line up:

- each numbered `bin/codex_wp` step starts emitting JSON quickly, beginning with `thread.started`
- `request1.final.txt` is exactly `REQ1 OK`
- `request2.final.txt` is exactly:

```text
STEP1 OK
STEP2 OK
FILE=alpha-beta
```

- `request3.final.txt` is exactly `PROXY CHECK OK`
- `status.after.json` still reports `"healthy": true`
- `doctor.after.json` shows no unexpected state regression compared with `doctor.before.json`
- `requests_total.delta` is at least `3`
- `events_total.delta` is at least `3`
- `request1.proxy.json`, `request2.proxy.json`, and `request3.proxy.json` each contain at least one `proxy.request` record
- each per-request proxy JSON file shows a non-empty `request_id`
- the per-request proxy records show `/responses` traffic with a success-like transport status such as `101` or `200`
- if there is only one attempt for a request, `attempt` remains `1`
- if there is a retry, the same `request_id` appears with `attempt` values `1`, `2`, and higher

Typical green-path interpretation:

- all three wrapper requests worked
- the proxy saw all three requests
- the management plane and persisted audit trail agreed on request growth

## Red Path Expectations

Treat the run as failed or suspicious when you see any of these signals:

- any numbered `bin/codex_wp` step does not emit JSON promptly, hangs before `thread.started`, or exits without `turn.completed`
- any per-request final output is missing, truncated, or different from the expected text
- `status.after.json` reports `"healthy": false`
- `/debug`, `/health`, or `/trace` fail with auth, connection, or timeout errors
- `requests_total.delta` is less than `3`
- `events_total.delta` is less than `3`
- any of `request1.proxy.json`, `request2.proxy.json`, or `request3.proxy.json` is empty
- the per-request delta files appended lines, but none of them are `proxy.request` events
- `trace.after.json` and the event log disagree about whether proxy requests happened
- `doctor.after.json` shows unexpected new cooldown or blacklist movement for this simple run
- the log tail shows repeated startup failures, missing auth files, or repeated upstream/proxy exceptions
- `request_id` is absent from proxy request events, or retries appear without shared `request_id`

Typical red-path interpretation:

- one or more wrapper requests did not traverse the proxy correctly
- the observability data is too weak to prove proxy usage
- the run cannot be trusted even if one request returned plausible text

## Validation

Mark the run as `pass` only when all of the following are true:

- `request1.jsonl`, `request2.jsonl`, and `request3.jsonl` each contain `thread.started`, `turn.started`, `item.completed`, and `turn.completed`
- `request1.final.txt`, `request2.final.txt`, and `request3.final.txt` match the expected outputs
- `requests_total.delta` is at least `3`
- `events_total.delta` is at least `3`
- each per-request proxy JSON file contains `proxy.request` evidence for `/responses`
- `status.after.json` reports `"healthy": true`

Mark the run as `revise` when `codex_wp` succeeds but observability is incomplete, for example:

- all three final answers are correct but one or more per-request proxy evidence files are empty
- the event log advanced but you cannot tie the new lines to a specific request step
- the proxy stayed healthy but doctor output changed unexpectedly

Mark the run as `blocked` when the wrapper or proxy flow cannot be trusted, for example:

- any numbered request hangs before JSON output starts
- `cdx status` is unhealthy after the run
- `/debug`, `/health`, or `/trace` cannot be read with the management key

## Traceability Rules

- `request_id` is the primary correlation key for proxy-side request attempts
- `attempt` must increase if the same inbound request is retried
- `auth_file` lets you confirm which credential handled each attempt
- `/trace` is the fast recent view; `rr_proxy_v2.events.jsonl` is the persisted audit trail

If you observe the same `request_id` with `attempt` values `1`, `2`, and higher, that is positive evidence that retry behavior remained traceable through the run.

## Output Format

Follow this format precisely when recording a run result.

```text
Result: pass | revise | blocked
Mode: manual-run
Scope:
- bin/codex_wp
Files changed:
- none
Applied precedence:
- docs/operations/codex_wp_observability_runbook.md: AGENTS.md -> consistency-codebase skill -> existing docs/CODEX_EXEC_INTEGRATION.md
Blocking issues:
- <issue or none>
Maintainability issues:
- <issue or none>
Notes:
- artifact_dir=<path>
- base_url=<url>
- final_message=<short summary>
```

## Notes

- `cdx trace` is useful for live observation, but `/trace` plus `rr_proxy_v2.events.jsonl` is better for step-by-step reproducibility.
- Intermediate `agent_message` items before the final answer are normal in `--json` mode; use the last completed agent message as the user-visible result.
- A simple successful run may show only one `attempt` for `/responses`; retries are not required for a passing smoke test.
- If you need to test retry traceability specifically, use a controlled failing upstream or a dedicated contract test such as `tests/taad/test_taad_traceability_contracts.py`.
