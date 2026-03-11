# Production Runbook: Auto Blacklist Management

## Overview

This runbook covers the auto-heal blacklist management system for cdx_proxy_cli_v2.

## System Architecture

### Components

1. **RoundRobinAuthPool** (`src/cdx_proxy_cli_v2/auth/rotation.py`)
   - Manages auth key rotation
   - Tracks blacklist/cooldown/probation states
   - Implements auto-heal logic

2. **Background Health Checker** (`src/cdx_proxy_cli_v2/proxy/server.py`)
   - Runs every 60 seconds (configurable)
   - Probes blacklisted keys with lightweight API calls
   - Restores keys after 2 successful checks

3. **Event Logger** (`src/cdx_proxy_cli_v2/observability/`)
   - Logs all major events to `rr_proxy_v2.events.jsonl`
   - Trace store for real-time monitoring

### Envoy-Inspired Features

| Feature | Description | Default |
|---------|-------------|---------|
| `consecutive_error_threshold` | Errors before blacklist | 3 |
| `auto_heal_interval` | Seconds between health checks | 60 |
| `auto_heal_success_target` | Successes to restore key | 2 |
| `auto_heal_max_attempts` | Failures before penalty | 3 |
| `max_ejection_percent` | Max % keys blacklisted | 50 |

## Configuration

### Environment Variables

```bash
# Auto-heal configuration
export CLIPROXY_AUTO_HEAL_INTERVAL=60          # Health check interval (seconds)
export CLIPROXY_AUTO_HEAL_SUCCESS_TARGET=2     # Successes to restore
export CLIPROXY_AUTO_HEAL_MAX_ATTEMPTS=3       # Failures before penalty
export CLIPROXY_MAX_EJECTION_PERCENT=50        # Max blacklist %
export CLIPROXY_CONSECUTIVE_ERROR_THRESHOLD=3  # Errors before blacklist
```

### CLI Options (future)

```bash
cdx proxy \
  --auto-heal-interval 60 \
  --auto-heal-success-target 2 \
  --auto-heal-max-attempts 3 \
  --max-ejection-percent 50 \
  --consecutive-error-threshold 3
```

## Monitoring

### Real-time Monitoring

```bash
# Watch live trace events
cdx trace

# View event log
tail -f ~/.codex/_auths/rr_proxy_v2.events.jsonl | jq .

# Check health status
cdx doctor
```

### Key Events

| Event | Level | Description | Action |
|-------|-------|-------------|--------|
| `auth.blacklisted` | WARN | Key ejected (401/403) | Monitor frequency |
| `auth.cooldown` | INFO | Key rate limited (429) | Normal operation |
| `auth.pool_exhausted` | ERROR | All keys unavailable | Investigate immediately |
| `auto_heal.success` | INFO | Key restored | Normal operation |
| `auto_heal.failure` | WARN | Health check failed | Monitor pattern |

### Metrics (future endpoint)

```bash
# Prometheus-format metrics (planned)
curl http://127.0.0.1:8080/stats/prometheus

# Expected metrics:
# cdx_auth_total 5
# cdx_auth_ok 3
# cdx_auth_blacklist 1
# cdx_auth_cooldown 1
# cdx_auto_heal_success_total 12
# cdx_auto_heal_failure_total 3
```

## Troubleshooting

### High Blacklist Rate

**Symptom:** Many `auth.blacklisted` events

**Possible Causes:**
1. Invalid/expired tokens
2. Upstream API issues
3. Network connectivity problems

**Actions:**
```bash
# Check which keys are blacklisted
cdx doctor

# View recent events
cdx trace

# Check token validity manually
curl -H "Authorization: Bearer <token>" https://chatgpt.com/backend-api/models

# Reset blacklisted keys if tokens are valid
cdx reset --state blacklist
```

### Pool Exhausted (503 Errors)

**Symptom:** `auth.pool_exhausted` events, 503 responses

**Possible Causes:**
1. All tokens expired
2. Upstream outage
3. Configuration issue (max_ejection_percent too low)

**Actions:**
```bash
# Immediate: Check all key states
cdx doctor

# If tokens are valid, reset all
cdx reset

# If upstream issue, wait for recovery
# Monitor with:
watch -n 5 'cdx status'
```

### Auto-heal Not Restoring Keys

**Symptom:** Keys remain blacklisted despite valid tokens

**Possible Causes:**
1. Health check endpoint unreachable
2. Health check timeout too short
3. Auto-heal disabled

**Actions:**
```bash
# Check auto-heal configuration
cat ~/.codex/_auths/.env | grep AUTO_HEAL

# Test health check endpoint manually
curl -H "Authorization: Bearer <token>" https://chatgpt.com/backend-api/models

# Check event log for auto_heal.failure events
grep auto_heal.failure ~/.codex/_auths/rr_proxy_v2.events.jsonl
```

### Performance Issues

**Symptom:** High latency, slow key rotation

**Possible Causes:**
1. Too frequent health checks
2. Too many keys
3. Network latency

**Actions:**
```bash
# Increase health check interval
export CLIPROXY_AUTO_HEAL_INTERVAL=120

# Check trace for latency patterns
cdx trace

# Monitor system resources
top -p $(cat ~/.codex/_auths/rr_proxy_v2.pid)
```

## Maintenance

### Regular Tasks

**Daily:**
- Monitor `cdx trace` for unusual patterns
- Check `cdx doctor` for key distribution

**Weekly:**
- Review event logs for trends
- Rotate tokens proactively

**Monthly:**
- Audit key usage patterns
- Update configuration based on metrics

### Token Rotation

```bash
# Add new token
python scripts/add_auth_token.py

# Verify new token works
cdx doctor

# Remove old token (if needed)
rm ~/.codex/_auths/old_token.json
```

## Escalation

### When to Escalate

1. Persistent `auth.pool_exhausted` after reset
2. Auto-heal failure rate > 50%
3. Unusual latency spikes (> 5 seconds)
4. Memory/CPU exhaustion

### Escalation Path

1. **L1:** Check runbook, run diagnostics
2. **L2:** Review logs, check upstream status
3. **L3:** Engage upstream provider, investigate code

## Appendix

### Configuration Reference

```yaml
# ~/.codex/_auths/config.yaml (future format)
auto_heal:
  enabled: true
  interval_seconds: 60
  success_target: 2
  max_attempts: 3
  check_path: "/backend-api/models"
  check_timeout_seconds: 5

outlier_detection:
  consecutive_errors: 3
  base_ejection_time_seconds: 900
  max_ejection_percent: 50
```

### Log Format

```json
{
  "ts": "2026-03-09T12:00:00.000Z",
  "level": "WARN",
  "event": "auth.blacklisted",
  "message": "Key user@example.com blacklisted (status 401)",
  "auth_file": "user.json",
  "auth_email": "user@example.com",
  "status": 401,
  "error_code": "token_invalid"
}
```

### Related Documentation

- [Auto-heal Roadmap](docs/auto_heal_roadmap.md)
- [TaaD Test Matrix](docs/quality/TAAD_TEST_MATRIX.md)
- [Operations Runbook](docs/operations/runbook.md)
