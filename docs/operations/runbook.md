# cdx_proxy_cli_v2 Runbook

## Start

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
pip install -e .
cdx2 proxy
```

If you need shell exports:

```bash
eval "$(cdx2 proxy --print-env)"
```

## Observe

- `cdx2 status`
- `cdx2 trace`
- `cdx2 logs --lines 150`

## Stop

```bash
cdx2 stop
```

## Runtime artifacts

- `~/.codex/_auths/rr_proxy_v2.pid`
- `~/.codex/_auths/rr_proxy_v2.state.json`
- `~/.codex/_auths/rr_proxy_v2.log`
- `~/.codex/_auths/rr_proxy_v2.events.jsonl`
