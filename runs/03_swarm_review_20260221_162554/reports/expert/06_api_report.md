# API Expert Report
# cdx_proxy_cli_v2 Swarm Review

run_id: "03_swarm_review_20260221_162554"
expert: api
phase: 2
timestamp: "2026-02-21T16:27:00+03:00"

## Executive Summary

Общая оценка API дизайна: **ХОРОШАЯ (7.5/10)**

RESTful management API с понятными endpoint-ами. CLI API следует Unix conventions.

## CLI API Analysis

### Commands

| Command | Purpose | Status |
|---------|---------|--------|
| `cdx2 proxy` | Start/reuse proxy | ✅ Well-designed |
| `cdx2 status` | Service status | ✅ JSON output available |
| `cdx2 stop` | Stop proxy | ✅ Simple |
| `cdx2 trace` | Live trace TUI | ✅ Good UX |
| `cdx2 logs` | Tail logs | ✅ Standard |
| `cdx2 doctor` | Auth health | ✅ Informative |
| `cdx2 all` | Key dashboard | ✅ V1 compatibility |
| `cdx2 reset` | Reset auth state | ✅ New in v2 |
| `cdx2 migrate` | V1→V2 migration | ✅ Good migration path |

### CLI Design Quality

### P1: Consistent Flag Naming (✅)
- **Evidence**: `--auth-dir`, `--host`, `--port` consistent across commands
- **Impact**: Predictable interface

### P1: JSON Output Option (✅)
- **Files**: `main.py:handle_status`, `main.py:handle_doctor`, `main.py:handle_all`
- **Evidence**: `--json` flag for machine-readable output
- **Impact**: Scriptable

### P1: Exit Code Semantics (✅)
- **File**: `src/cdx_proxy_cli_v2/cli/main.py:370-380`
- **Evidence**: Documented exit codes (0=success, 1=runtime error, 2=user error, 130=interrupted)
- **Impact**: Proper Unix conventions

## HTTP Management API Analysis

### Endpoints

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/debug` | GET | Runtime info | X-Management-Key |
| `/trace` | GET | Trace events | X-Management-Key |
| `/health` | GET | Auth health | X-Management-Key |
| `/auth-files` | GET | Auth file list | X-Management-Key |
| `/shutdown` | POST | Graceful stop | X-Management-Key |
| `/reset` | POST | Reset auth state | X-Management-Key |

### P1: Consistent JSON Responses (✅)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py:152-157`
- **Evidence**: `_send_json()` helper for consistent format
- **Impact**: Predictable response structure

### P1: Proper HTTP Methods (✅)
- **Evidence**: GET for reads, POST for mutations
- **Impact**: RESTful design

### P2: Query Parameters (✅)
- **Evidence**: `/health?refresh=1`, `/trace?limit=200`, `/reset?name=x&state=y`
- **Impact**: Flexible queries

## API Concerns

### P0: No API Versioning (⚠️)
- **Issue**: Endpoints have no version prefix
- **Impact**: Breaking changes affect all clients
- **Recommendation**: Add `/v1/` prefix for future-proofing
- **Risk Level**: MEDIUM

### P1: No OpenAPI Spec (⚠️)
- **Issue**: No formal API specification
- **Impact**: Hard for clients to discover API
- **Recommendation**: Generate OpenAPI spec
- **Risk Level**: MEDIUM

### P1: Error Response Format (⚠️)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py`
- **Evidence**: `{"error": "message"}` format
- **Issue**: No error codes or structured details
- **Recommendation**: Add `code` and `details` fields
- **Risk Level**: LOW

### P2: No Pagination for /trace (⚠️)
- **File**: `src/cdx_proxy_cli_v2/proxy/server.py:185-195`
- **Evidence**: `limit` parameter but no offset
- **Issue**: Can't page through large trace histories
- **Recommendation**: Add `offset` parameter
- **Risk Level**: LOW

## Proxy Behavior (Passthrough API)

### P1: Transparent Proxying (✅)
- **Evidence**: Request/response passed through with auth injection
- **Impact**: Compatible with OpenAI API contract

### P1: Header Rewriting (✅)
- **File**: `src/cdx_proxy_cli_v2/proxy/rules.py:85-105`
- **Evidence**: `build_forward_headers()` with sensible filtering
- **Impact**: Clean request forwarding

## Recommendations

1. **P0**: Add `/v1/` prefix to management endpoints
2. **P1**: Generate OpenAPI specification
3. **P1**: Enhance error responses with codes
4. **P2**: Add pagination to `/trace` endpoint

## Confidence

- **confidence_percent**: 87
- **files_analyzed**: 8
- **evidence_citations**: 14
