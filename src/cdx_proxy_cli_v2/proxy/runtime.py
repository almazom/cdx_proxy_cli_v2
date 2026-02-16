"""Proxy runtime state and coordination."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cdx_proxy_cli_v2.auth.rotation import RoundRobinAuthPool
from cdx_proxy_cli_v2.config.settings import Settings
from cdx_proxy_cli_v2.observability.event_log import EventLogger
from cdx_proxy_cli_v2.observability.trace_store import TraceStore
from cdx_proxy_cli_v2.proxy.connection_pool import ConnectionPool


@dataclass
class ProxyRuntime:
    """Coordinates proxy state including auth pool, tracing, logging, and connections.
    
    This class manages all runtime state for the proxy server:
    - Auth pool: Round-robin selection with cooldown/blacklist support
    - Connection pool: Reusable HTTP connections for upstream requests
    - Trace store: In-memory ring buffer for request tracing
    - Event logger: Persistent JSONL event log
    """
    
    settings: Settings
    auth_pool: RoundRobinAuthPool = field(default_factory=RoundRobinAuthPool)
    connection_pool: ConnectionPool = field(default_factory=ConnectionPool)
    trace_store: TraceStore = field(init=False)
    logger: EventLogger = field(init=False)

    def __post_init__(self) -> None:
        self.trace_store = TraceStore(max_size=self.settings.trace_max)
        self.logger = EventLogger(self.settings.auth_dir)

    def reload_auths(self) -> int:
        """Reload auth records from disk. Returns count of loaded records."""
        from cdx_proxy_cli_v2.auth.store import load_auth_records
        records = load_auth_records(self.settings.auth_dir)
        self.auth_pool.load(records)
        return len(records)

    def health_snapshot(self, *, refresh: bool = False) -> Dict[str, Any]:
        """Get health snapshot of all auth accounts.
        
        Args:
            refresh: If True, reload auths from disk before snapshot
        """
        if refresh:
            self.reload_auths()
        accounts = self.auth_pool.health_snapshot()
        return {
            "ok": bool(accounts),
            "accounts": accounts,
        }

    def trace_events(self, limit: int) -> List[Dict[str, Any]]:
        """Get recent trace events.
        
        Args:
            limit: Maximum number of events to return (0 = all)
        """
        return self.trace_store.list(limit=limit)

    def debug_payload(self, *, host: str, port: int) -> Dict[str, Any]:
        """Get debug information payload.
        
        Args:
            host: Server host address
            port: Server port number
        """
        return {
            "status": "running",
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
            "auth_dir": self.settings.auth_dir,
            "auth_count": self.auth_pool.count(),
            "upstream_base_url": self.settings.upstream,
            "log_request_preview": False,
            "management_key_required": bool(self.settings.management_key),
            "trace_max": self.trace_store.max_size,
            "pid": os.getpid(),
            "event_log_file": str(self.logger.path),
        }

    def record_attempt(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        route: str,
        status: int,
        latency_ms: int,
        auth_name: str,
        auth_email: Optional[str],
        attempt: int,
        client_ip: Optional[str],
        error: Optional[str] = None,
    ) -> None:
        """Record a request attempt in trace store and event log.
        
        Args:
            request_id: Unique identifier for the request
            method: HTTP method (GET, POST, etc.)
            path: Request path
            route: Route classification (request, compact, other)
            status: HTTP response status code
            latency_ms: Request latency in milliseconds
            auth_name: Auth file name used
            auth_email: Auth email if available
            attempt: Attempt number (1-indexed)
            client_ip: Client IP address
            error: Error message if request failed
        """
        payload: Dict[str, Any] = {
            "ts": time.time(),
            "request_id": request_id,
            "method": method,
            "path": path,
            "route": route,
            "status": status,
            "latency_ms": latency_ms,
            "auth_file": auth_name,
            "auth_email": auth_email,
            "attempt": attempt,
            "client_ip": client_ip,
        }
        if error:
            payload["error"] = error
        self.trace_store.add(payload)
        self.logger.write(
            level="INFO" if status < 500 else "WARN",
            event="proxy.request",
            message="request attempt completed",
            **payload,
        )

    def shutdown(self) -> None:
        """Clean up resources on shutdown."""
        self.connection_pool.close_all()
