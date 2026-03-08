# 🚀 cdx_proxy_cli_v2 Swarm Review Kickoff

## 🎯 Mission

Execute a comprehensive code review and improvement cycle for `cdx_proxy_cli_v2` using the 03_swarm_review v4.0.18 protocol with non-stop execution through phases 0.0 to 9.

## 🔄 Execution Protocol

### Phase Flow
```
0.0 → 0.1 → 0.2 → 0.3 → 1 → 2 → 3 → 3.5 → 4 → 5 → 6 → 6.5 → 7 → 
8.1 → 8.2 → 8.2.2 → 8.2.3 → 8.2.4 → 8.2.1 → 8.3 → 8.4 → 8.5 → 8.6 → 
8.6.1 → 8.7 → 8.8 → 8.8.1 → 8.9.0 → 8.9 → 8.9.1 → 9 → 9.1
```

### Non-Stop Guarantee
- **NEVER_STOP:** All phases execute without user intervention
- **Auto-Rollback:** On failure, trigger phase 8.8 remediation
- **Quality Gate:** Minimum 95% score for READY status

## 📁 Files

```
src/cdx_proxy_cli_v2/
├── auth/
│   ├── store.py          # Token storage and extraction
│   └── rotation.py       # Round-robin token rotation
├── proxy/
│   ├── server.py         # HTTP proxy transport
│   ├── rules.py          # Request routing/rewriting
│   ├── runtime.py        # Proxy runtime state
│   ├── http_client.py    # HTTP client wrapper
│   └── management.py     # Management endpoints
├── observability/
│   ├── trace_store.py    # In-memory trace ring buffer
│   ├── event_log.py      # JSONL event sink
│   ├── tui.py            # Rich live trace monitor
│   ├── dashboard.py      # Collective dashboard
│   └── all_dashboard.py  # All-in-one dashboard
├── config/
│   └── settings.py       # Runtime/env configuration
├── runtime/
│   └── service.py        # Background process lifecycle
└── cli/
    └── main.py           # Command orchestration
```

## 🚀 Getting Started

1. Review [BOARD.md](./BOARD.md) for card inventory
2. Pick highest priority P0 card first
3. Execute implementation per card strategy
4. Auto-commit after each card
5. Proceed to PR creation after all cards

## ✅ Completion Criteria

- [ ] All 6 cards implemented
- [ ] Quality score >= 95%
- [ ] All tests passing
- [ ] No P0 regressions
- [ ] PR created with evidence

## 🎯 Git Flow Enforcement

```bash
# Branch naming: swarm-review-run-{RUN_ID}
# Commit format: card({ID}): {description}
# Merge strategy: Squash with traceability
```
