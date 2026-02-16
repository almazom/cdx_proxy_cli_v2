"""HTTP connection pooling for upstream requests."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import Dict, List, Optional, Tuple


@dataclass
class PooledConnection:
    """Wrapper for a pooled HTTP connection with metadata."""
    connection: HTTPConnection
    host: str
    port: int
    created_at: float
    last_used: float
    use_count: int = 0

    def is_stale(self, max_age_seconds: float = 300.0) -> bool:
        """Check if connection has been idle too long."""
        return (time.time() - self.last_used) > max_age_seconds

    def touch(self) -> None:
        """Update last-used timestamp and increment use count."""
        self.last_used = time.time()
        self.use_count += 1


class ConnectionPool:
    """Thread-safe HTTP connection pool.
    
    Maintains a pool of reusable HTTP connections per host.
    Connections are reused until they become stale or encounter errors.
    """

    DEFAULT_POOL_SIZE = 10
    DEFAULT_MAX_AGE_SECONDS = 300.0  # 5 minutes
    DEFAULT_TIMEOUT = 25

    def __init__(
        self,
        max_pool_size: int = DEFAULT_POOL_SIZE,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        default_timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._max_pool_size = max(1, max_pool_size)
        self._max_age_seconds = max_age_seconds
        self._default_timeout = default_timeout
        self._pools: Dict[str, List[PooledConnection]] = {}
        self._lock = threading.Lock()

    def _pool_key(self, scheme: str, host: str, port: int) -> str:
        return f"{scheme}://{host}:{port}"

    def _create_connection(
        self,
        scheme: str,
        host: str,
        port: int,
        timeout: int,
    ) -> PooledConnection:
        """Create a new connection."""
        now = time.time()
        conn_cls = HTTPSConnection if scheme == "https" else HTTPConnection
        connection = conn_cls(host, port, timeout=timeout)
        return PooledConnection(
            connection=connection,
            host=host,
            port=port,
            created_at=now,
            last_used=now,
        )

    def acquire(
        self,
        scheme: str,
        host: str,
        port: int,
        timeout: Optional[int] = None,
    ) -> Tuple[PooledConnection, bool]:
        """Acquire a connection from the pool.
        
        Returns:
            Tuple of (PooledConnection, is_new) where is_new indicates
            if a new connection was created.
        """
        key = self._pool_key(scheme, host, port)
        effective_timeout = timeout or self._default_timeout

        with self._lock:
            pool = self._pools.get(key, [])
            
            # Try to find a usable connection
            for i, pooled in enumerate(pool):
                if not pooled.is_stale(self._max_age_seconds):
                    # Test if connection is still valid
                    try:
                        # Simple check - if we can get the sock attribute, it's alive
                        _ = pooled.connection.sock
                        pooled.touch()
                        # Remove from pool while in use
                        pool.pop(i)
                        self._pools[key] = pool
                        return pooled, False
                    except Exception:
                        # Connection is dead, remove it
                        pool.pop(i)
                        self._pools[key] = pool
                        break
                else:
                    # Stale connection, remove it
                    try:
                        pooled.connection.close()
                    except Exception:
                        pass
                    pool.pop(i)
                    self._pools[key] = pool
                    break

            # Create new connection if pool has room
            pooled = self._create_connection(scheme, host, port, effective_timeout)
            return pooled, True

    def release(self, pooled: PooledConnection, scheme: str, host: str, port: int) -> None:
        """Return a connection to the pool for reuse."""
        key = self._pool_key(scheme, host, port)

        with self._lock:
            pool = self._pools.get(key, [])
            
            if len(pool) < self._max_pool_size and not pooled.is_stale(self._max_age_seconds):
                pool.append(pooled)
                self._pools[key] = pool
            else:
                # Pool full or connection stale, close it
                try:
                    pooled.connection.close()
                except Exception:
                    pass

    def close_all(self) -> None:
        """Close all pooled connections."""
        with self._lock:
            for pool in self._pools.values():
                for pooled in pool:
                    try:
                        pooled.connection.close()
                    except Exception:
                        pass
            self._pools.clear()

    def stats(self) -> Dict[str, int]:
        """Return pool statistics."""
        with self._lock:
            return {
                "hosts": len(self._pools),
                "total_connections": sum(len(p) for p in self._pools.values()),
            }
