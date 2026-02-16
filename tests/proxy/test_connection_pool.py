"""Tests for HTTP connection pooling."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from cdx_proxy_cli_v2.proxy.connection_pool import (
    ConnectionPool,
    PooledConnection,
)


class TestPooledConnection:
    """Tests for PooledConnection class."""

    def test_is_stale_returns_false_for_fresh_connection(self):
        """Fresh connections should not be considered stale."""
        mock_conn = MagicMock()
        pooled = PooledConnection(
            connection=mock_conn,
            host="example.com",
            port=443,
            created_at=time.time(),
            last_used=time.time(),
        )
        assert not pooled.is_stale(max_age_seconds=300.0)

    def test_is_stale_returns_true_for_old_connection(self):
        """Connections idle longer than max_age should be stale."""
        mock_conn = MagicMock()
        pooled = PooledConnection(
            connection=mock_conn,
            host="example.com",
            port=443,
            created_at=time.time() - 400,
            last_used=time.time() - 400,
        )
        assert pooled.is_stale(max_age_seconds=300.0)

    def test_touch_updates_timestamp(self):
        """touch() should update last_used and increment use_count."""
        mock_conn = MagicMock()
        pooled = PooledConnection(
            connection=mock_conn,
            host="example.com",
            port=443,
            created_at=time.time() - 100,
            last_used=time.time() - 100,
            use_count=0,
        )
        
        pooled.touch()
        
        assert pooled.last_used > time.time() - 1
        assert pooled.use_count == 1


class TestConnectionPool:
    """Tests for ConnectionPool class."""

    def test_acquire_returns_new_connection_first_time(self):
        """First acquire for a host should create a new connection."""
        pool = ConnectionPool()
        
        with patch.object(pool, '_create_connection') as mock_create:
            mock_pooled = MagicMock()
            mock_pooled.is_stale.return_value = False
            mock_pooled.connection.sock = True
            mock_create.return_value = mock_pooled
            
            conn, is_new = pool.acquire('https', 'example.com', 443)
            
            assert is_new is True
            mock_create.assert_called_once()

    def test_release_returns_connection_to_pool(self):
        """release() should add connection back to pool."""
        pool = ConnectionPool(max_pool_size=5)
        
        mock_pooled = MagicMock()
        mock_pooled.is_stale.return_value = False
        
        pool.release(mock_pooled, 'https', 'example.com', 443)
        
        stats = pool.stats()
        assert stats['total_connections'] == 1

    def test_pool_respects_max_size(self):
        """Pool should not exceed max_pool_size."""
        pool = ConnectionPool(max_pool_size=2)
        
        mock_pooled1 = MagicMock()
        mock_pooled1.is_stale.return_value = False
        mock_pooled2 = MagicMock()
        mock_pooled2.is_stale.return_value = False
        mock_pooled3 = MagicMock()
        mock_pooled3.is_stale.return_value = False
        
        pool.release(mock_pooled1, 'https', 'example.com', 443)
        pool.release(mock_pooled2, 'https', 'example.com', 443)
        pool.release(mock_pooled3, 'https', 'example.com', 443)
        
        stats = pool.stats()
        assert stats['total_connections'] == 2
        mock_pooled3.connection.close.assert_called_once()

    def test_close_all_cleans_up(self):
        """close_all() should close and remove all connections."""
        pool = ConnectionPool()
        
        mock_pooled = MagicMock()
        mock_pooled.is_stale.return_value = False
        
        pool.release(mock_pooled, 'https', 'example.com', 443)
        
        pool.close_all()
        
        stats = pool.stats()
        assert stats['total_connections'] == 0
        mock_pooled.connection.close.assert_called_once()

    def test_acquire_reuses_pooled_connection(self):
        """Second acquire should reuse pooled connection."""
        pool = ConnectionPool()
        
        mock_pooled = MagicMock()
        mock_pooled.is_stale.return_value = False
        mock_pooled.connection.sock = True
        
        # First, add a connection to the pool
        pool.release(mock_pooled, 'https', 'example.com', 443)
        
        # Now acquire should reuse it
        conn, is_new = pool.acquire('https', 'example.com', 443)
        
        assert is_new is False
        assert conn == mock_pooled

    def test_pool_key_format(self):
        """Pool key should uniquely identify scheme/host/port."""
        pool = ConnectionPool()
        
        key1 = pool._pool_key('https', 'example.com', 443)
        key2 = pool._pool_key('http', 'example.com', 80)
        key3 = pool._pool_key('https', 'other.com', 443)
        
        assert key1 == 'https://example.com:443'
        assert key2 == 'http://example.com:80'
        assert key1 != key2
        assert key1 != key3

    def test_stale_connection_is_closed_on_acquire(self):
        """Stale connections should be closed when encountered."""
        pool = ConnectionPool(max_pool_size=5)
        
        mock_pooled = MagicMock()
        mock_pooled.is_stale.return_value = True  # Stale connection
        
        pool.release(mock_pooled, 'https', 'example.com', 443)
        
        # Acquire should create new connection and close stale one
        with patch.object(pool, '_create_connection') as mock_create:
            new_pooled = MagicMock()
            new_pooled.is_stale.return_value = False
            mock_create.return_value = new_pooled
            
            conn, is_new = pool.acquire('https', 'example.com', 443)
            
            assert is_new is True
            mock_pooled.connection.close.assert_called_once()

    def test_separate_pools_for_different_hosts(self):
        """Different hosts should have separate connection pools."""
        pool = ConnectionPool()
        
        mock_pooled1 = MagicMock()
        mock_pooled1.is_stale.return_value = False
        mock_pooled2 = MagicMock()
        mock_pooled2.is_stale.return_value = False
        
        pool.release(mock_pooled1, 'https', 'example.com', 443)
        pool.release(mock_pooled2, 'https', 'other.com', 443)
        
        stats = pool.stats()
        assert stats['hosts'] == 2
        assert stats['total_connections'] == 2
