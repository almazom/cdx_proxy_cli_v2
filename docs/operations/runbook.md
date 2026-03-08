# cdx_proxy_cli_v2 Runbook

## Start

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
pip install -e .
cdx proxy
```

If you need shell exports:

```bash
eval "$(cdx proxy --print-env-only)"
```

## Observe

- `cdx status`
- `cdx trace`
- `cdx logs --lines 150`

## Stop

```bash
cdx stop
```

## Runtime artifacts

- `~/.codex/_auths/rr_proxy_v2.pid`
- `~/.codex/_auths/rr_proxy_v2.state.json`
- `~/.codex/_auths/rr_proxy_v2.log`
- `~/.codex/_auths/rr_proxy_v2.events.jsonl`
