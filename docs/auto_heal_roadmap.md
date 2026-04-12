# Roadmap to 95%+ Confidence: Auto Blacklist Management

## Current State (75% confidence)

✅ Auto-heal background checker implemented
✅ User notifications for major events
✅ 209 tests passing
✅ Basic documentation

## Gaps to Address

### 1. Configuration Flexibility (Envoy-inspired)

**Envoy Pattern:** All outlier detection parameters are configurable via cluster settings.

**Current Gap:** Auto-heal uses hardcoded constants.

**Fix:**
```python
# Add to Settings dataclass
auto_heal_interval: int = 60        # Check interval seconds
auto_heal_success_target: int = 2   # Successes needed to restore
auto_heal_max_attempts: int = 3     # Failures before penalty
```

**Envoy Reference:**
- `outlierDetection.interval` (default: 10s)
- `outlierDetection.successfulThreshold` (default: 1)
- `outlierDetection.consecutive5xx` (default: 5)

---

### 2. Max Ejection Percent (Envoy Pattern)

**Envoy Pattern:** Never eject more than X% of endpoints to prevent total outage.

**Current Gap:** All keys can be blacklisted simultaneously → 503 errors.

**Fix:**
```python
# In RoundRobinAuthPool.pick()
def pick(self) -> Optional[AuthState]:
    # ... existing code ...
    
    # Envoy: max_ejection_percent (default: 10%)
    max_blacklist = max(1, int(total_keys * 0.9))  # Keep at least 10% available
    if len(blacklisted) > max_blacklist:
        # Force-eject some keys back to available
        self._force_restore_least_failed(blacklisted, max_blacklist)
```

**Envoy Reference:**
- `outlierDetection.maxEjectionPercent` (default: 10%)
- `outlierDetection.enforcingMaxEjectionPercent` (default: 100%)

---

### 3. Consecutive Error Threshold (Envoy Pattern)

**Envoy Pattern:** Eject only after N consecutive errors, not single failure.

**Current Gap:** Single 401/403 immediately blacklists.

**Fix:**
```python
# Add to AuthState
consecutive_errors: int = 0

# In mark_result()
if status in {401, 403}:
    state.consecutive_errors += 1
    if state.consecutive_errors >= CONSECUTIVE_ERROR_THRESHOLD:
        self._mark_blacklist(state, now, reason="consecutive_errors")
else:
    state.consecutive_errors = 0  # Reset on success
```

**Envoy Reference:**
- `outlierDetection.consecutive5xx` (default: 5)
- `outlierDetection.consecutiveGatewayError` (default: 5)

---

### 4. Metrics/Stats Endpoint (Envoy Pattern)

**Envoy Pattern:** `/stats` endpoint with Prometheus-format metrics.

**Current Gap:** No structured metrics for monitoring.

**Fix:**
```python
# Add to management endpoints
def handle_stats(args) -> int:
    stats = runtime.auth_pool.stats()
    # Output in Prometheus format:
    # cdx_auth_total 5
    # cdx_auth_ok 3
    # cdx_auth_blacklist 1
    # cdx_auth_cooldown 1
    # cdx_auto_heal_success_total 12
    # cdx_auto_heal_failure_total 3
```

**Envoy Reference:**
- `/stats` endpoint (Prometheus, JSON, text formats)
- `/stats/prometheus` for metrics scraping

---

### 5. Health Check Endpoint Customization

**Envoy Pattern:** Configurable health check path per cluster.

**Current Gap:** Hardcoded `/backend-api/models`.

**Fix:**
```python
# Add to Settings
auto_heal_check_path: str = "/backend-api/models"
auto_heal_check_method: str = "GET"
auto_heal_check_timeout: float = 5.0
```

---

### 6. Weighted Auth Keys (Envoy Pattern)

**Envoy Pattern:** Endpoints have weights for load balancing.

**Current Gap:** All keys treated equally.

**Fix:**
```python
# Add to AuthRecord
weight: int = 100  # Default weight

# In pick()
# Prefer higher-weight keys when multiple available
```

**Envoy Reference:**
- `loadBalancingPolicy: WEIGHTED_ROUND_ROBIN`
- Endpoint weight configuration

---

### 7. Priority/Failover (Envoy Pattern)

**Envoy Pattern:** Endpoints organized in priority levels (P0, P1, P2).

**Current Gap:** No priority tiers for auth keys.

**Fix:**
```python
# Add to AuthRecord
priority: int = 0  # 0 = highest, 1 = failover

# In pick()
# Always try P0 keys first, only use P1 if all P0 unavailable
```

**Envoy Reference:**
- `priority` field in endpoints
- `priority_weight` for cross-priority load balancing

---

### 8. Connection Pool Limits (Envoy Pattern)

**Envoy Pattern:** Circuit breakers limit concurrent connections/requests.

**Current Gap:** No rate limiting per auth key.

**Fix:**
```python
# Add to AuthState
concurrent_requests: int = 0
max_concurrent_requests: int = 10  # Per-key limit

# In pick()
if state.concurrent_requests >= state.max_concurrent_requests:
    continue  # Skip this key, circuit breaker tripped
```

**Envoy Reference:**
- `circuitBreakers.thresholds.maxConnections`
- `circuitBreakers.thresholds.maxRequests`
- `circuitBreakers.thresholds.maxPendingRequests`

---

### 9. Retry Budget (Envoy Pattern)

**Envoy Pattern:** Limit retry traffic to prevent cascade.

**Current Gap:** Unlimited retries on 401/403.

**Fix:**
```python
# Add to Settings
max_retry_budget: float = 0.2  # 20% of traffic can be retries

# Track retry ratio
retry_count / total_requests > max_retry_budget → stop retrying
```

**Envoy Reference:**
- `retryBudget.budgetPercent` (default: 20%)
- `retryBudget.minRetryConcurrency`

---

### 10. Observability Enhancements

**Envoy Pattern:** Access logs, distributed tracing, detailed stats.

**Current Gap:** Basic trace events only.

**Fix:**
```python
# Add access log format
access_log_format: str = (
    "%START_TIME% %REQ(:METHOD)% %REQ(:PATH)% "
    "%RESPONSE_CODE% %AUTH_FILE% %DURATION%ms"
)

# Add request/response headers to trace
trace_headers: List[str] = ["x-request-id", "user-agent"]
```

**Envoy Reference:**
- `accessLog` configuration
- Distributed tracing (Zipkin, Jaeger, Lightstep)
- `requestHeadersToAdd`, `responseHeadersToAdd`

---

## Implementation Priority

| Priority | Feature | Effort | Impact |

---

## Newly Implemented Diagnostic Surfaces

### Failure Origin Classification

The runtime now classifies auto-heal probe failures with explicit origin values instead of treating every failure as a generic blacklist extension.

Current failure-origin vocabulary:

- `hard_auth`
- `quota`
- `probe_transport`
- `upstream_transient`

This helps operators distinguish between:

- invalid or forbidden auth material
- quota pressure and `429` conditions
- transport-level probe failures
- transient upstream failures that do not imply broken credentials

### Triage Summary Surfaces

The runtime now exposes a compact triage summary so operators do not need to infer pool state by stitching together multiple raw views.

Current surfaces:

- `/debug` includes `triage_summary`
- `/health` includes a compact `triage` object
- `cdx status` prints a one-line pool verdict and includes `triage_summary` in `--json`

The summary is built from `degraded_state_verdict()` and includes:

- `state`
- `primary_blocker`
- `next_action`

This closes a major observability gap from the earlier roadmap phases: operators can now see both the current degraded state and the recommended next step without manually correlating `cdx doctor`, `cdx trace`, and raw event logs first.
|----------|---------|--------|--------|
| P0 | Configurable settings | Low | High |
| P0 | Max ejection percent | Low | High |
| P1 | Consecutive error threshold | Medium | High |
| P1 | Metrics endpoint | Medium | Medium |
| P2 | Health check customization | Low | Low |
| P2 | Integration tests | Medium | High |
| P3 | Weighted keys | High | Low |
| P3 | Priority tiers | High | Low |
| P3 | Connection pool limits | High | Medium |

---

## Acceptance Criteria for 95%+

- [ ] All configuration options exposed via CLI/env
- [ ] Max ejection percent prevents total blackout
- [ ] Consecutive error threshold reduces false positives
- [ ] Metrics endpoint for monitoring
- [ ] Integration test validates auto-heal end-to-end
- [ ] Production runbook with troubleshooting guide
- [ ] 95%+ test coverage on auto-heal code
- [ ] Load tested with realistic workload

---

## Envoy-Inspired Configuration Schema

```yaml
# ~/.codex/_auths/config.yaml (future)
auto_heal:
  enabled: true
  interval_seconds: 60
  success_target: 2
  max_attempts: 3
  check_path: "/backend-api/models"
  check_timeout_seconds: 5

outlier_detection:
  consecutive_errors: 3
  interval_seconds: 30
  base_ejection_time_seconds: 900  # 15 min
  max_ejection_percent: 50
  enforcing_max_ejection_percent: 100

circuit_breaker:
  max_connections_per_key: 10
  max_requests_per_key: 100
  max_pending_requests: 50

retry_budget:
  budget_percent: 20
  min_retry_concurrency: 5
```

---

## Testing Strategy

1. **Unit tests** (done: 9 tests) → Expand to 20+ tests
2. **Integration tests** (todo: 5+ scenarios)
3. **Load tests** (todo: simulate 1000 requests/min)
4. **Chaos tests** (todo: random key failures)
5. **Production validation** (todo: 1 week monitoring)

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Test coverage | 75% | 95% |
| Auto-heal success rate | Unknown | >90% |
| False positive blacklist | Unknown | <5% |
| Manual reset frequency | Baseline | -80% |
| Mean time to recovery | ~15 min | <2 min |
