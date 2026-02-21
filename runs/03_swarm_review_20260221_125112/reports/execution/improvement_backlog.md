# Improvement Backlog — Run 03_swarm_review_20260221_125112

## P0 (Implement First)

- [ ] CARD-001 — Per-IP rate limiting (server.py:326, 2h)
- [ ] CARD-002 — Enforce response body size limit (server.py:35, 2h)

## P1 (Implement in Next Sprint)

- [ ] CARD-003 — Fix _read_body() socket timeout (server.py:211, 1h)
- [ ] CARD-004 — EventLogger persistent handle + NullEventLogger (event_log.py, 2h)
- [ ] CARD-005 — Split server.py: extract ProxyForwarder (server.py, 3h)
- [ ] CARD-006 — Settings schema validation (settings.py, 2h)
- [ ] CARD-007 — Management API /v1/ versioning (rules.py, 2h)
- [ ] CARD-008 — Concurrent stress test for auth rotation (test_rotation.py, 2h)
- [ ] CARD-009 — /trace endpoint pagination (server.py, 1h)

## P2 (Do When Stable)

- [ ] CARD-010 — Remove /debug filesystem path leakage (server.py, 1h)
- [ ] CARD-011 — Refactor build_forward_headers() (rules.py, 1h)
- [ ] CARD-012 — Cap ThreadingHTTPServer threads (server.py, 2h)

## SSOT Updates Needed in SSOT_KANBAN.yaml

- Close TASK-003 (TraceStore leak — resolved by deque)
- Close TASK-005 (Event log sanitization — implemented)
- Downgrade TASK-002 to P1 verification (add CARD-008 as subtask)
- Close TASK-001.3 (request size limit — done)
