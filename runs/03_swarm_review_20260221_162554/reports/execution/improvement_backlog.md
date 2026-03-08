# Improvement Backlog
# Phase 9 - Low priority improvements for future sprints

backlog_type: improvement
run_id: "03_swarm_review_20260221_162554"
phase: 9
timestamp: "2026-02-21T16:35:00+03:00"

## P3 Items

p3_items:
  - id: P3-001
    title: "Make management key length configurable"
    priority: P3
    estimated_hours: 0.5
    file: "src/cdx_proxy_cli_v2/config/settings.py"
    status: backlog

## Backlog Items

backlog_items:
  - id: BACKLOG-001
    title: "Add async I/O support"
    priority: BACKLOG
    estimated_hours: 40
    note: "Threading is currently sufficient - defer to future major version"
    status: deferred

## Future Considerations

future_considerations:
  - item: "WebSocket support for real-time trace updates"
    rationale: "Would improve TUX experience"
    priority: low
    
  - item: "Multi-upstream support"
    rationale: "Would enable fallback to different API providers"
    priority: low
    
  - item: "Metrics export (Prometheus format)"
    rationale: "Would enable better observability integration"
    priority: medium
    
  - item: "Plugin architecture for auth providers"
    rationale: "Would enable custom auth strategies"
    priority: low

## Technical Debt

technical_debt:
  - id: TD-001
    description: "Large CLI main.py file (380+ lines)"
    cards: [CARD-007, CARD-008]
    scheduled: Sprint 2
    
  - id: TD-002
    description: "Large proxy/server.py file (460+ lines)"
    cards: [CARD-002, CARD-021, CARD-022]
    scheduled: Sprint 4

## Summary

summary:
  p3_items: 1
  backlog_items: 1
  future_considerations: 4
  technical_debt_items: 2
  total_hours_backlog: 40.5
