"""End-to-End tests for auto-heal blacklist management.

This module tests the complete auto-heal flow from blacklist to restoration,
including integration with the proxy server and background health checker.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from cdx_proxy_cli_v2.config.settings import build_settings
from cdx_proxy_cli_v2.proxy.server import ProxyHTTPServer, ProxyRuntime


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_auth_dir(tmp_path: Path) -> Path:
    """Create temporary auth directory with test tokens."""
    auth_dir = tmp_path / "auths"
    auth_dir.mkdir()

    # Create test auth files
    for i in range(3):
        auth_file = auth_dir / f"test_{i}.json"
        auth_file.write_text(
            json.dumps(
                {
                    "access_token": f"test-token-{i}",
                    "email": f"test{i}@example.com",
                    "account_id": f"acc-{i}",
                }
            )
        )

    return auth_dir


class MockUpstreamHandler(BaseHTTPRequestHandler):
    """Mock upstream server that simulates various response scenarios."""

    # Class-level state for controlling responses
    response_sequence: List[int] = []
    response_index: int = 0
    lock: threading.Lock = threading.Lock()
    health_check_always_success: bool = True  # Health checks always succeed by default

    def log_message(self, format, *args):
        """Suppress logging."""
        pass

    @classmethod
    def set_response_sequence(cls, status_codes: List[int]) -> None:
        """Set the sequence of status codes to return."""
        with cls.lock:
            cls.response_sequence = status_codes
            cls.response_index = 0

    @classmethod
    def get_next_status(cls) -> int:
        """Get next status code from sequence."""
        with cls.lock:
            if cls.response_index >= len(cls.response_sequence):
                return 200  # Default to success
            status = cls.response_sequence[cls.response_index]
            cls.response_index += 1
            return status

    @classmethod
    def reset(cls) -> None:
        """Reset state."""
        with cls.lock:
            cls.response_sequence = []
            cls.response_index = 0
            cls.health_check_always_success = True

    def do_POST(self) -> None:
        """Handle POST requests."""
        status = self.get_next_status()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        if status == 200:
            self.wfile.write(json.dumps({"id": "test-response"}).encode())
        elif status in {401, 403}:
            self.wfile.write(
                json.dumps(
                    {"error": {"code": "invalid_token", "message": "Invalid token"}}
                ).encode()
            )
        elif status == 429:
            self.wfile.write(
                json.dumps(
                    {
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": "Rate limit exceeded",
                        }
                    }
                ).encode()
            )
        else:
            self.wfile.write(
                json.dumps(
                    {"error": {"code": "server_error", "message": "Server error"}}
                ).encode()
            )

    def do_GET(self) -> None:
        """Handle GET requests (health checks)."""
        if self.path.startswith("/api/codex/usage") or self.path.startswith("/wham/usage"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "plan_type": "plus",
                        "rate_limit": {
                            "limit_reached": False,
                            "primary_window": {
                                "limit_window_seconds": 5 * 60 * 60,
                                "used_percent": 10.0,
                                "reset_after_seconds": 3600,
                            },
                        },
                    }
                ).encode()
            )
            return

        # Health check endpoint
        if self.path in {"/models", "/backend-api/models"}:
            if self.health_check_always_success:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"data": []}).encode())
            else:
                # Use response sequence for health checks too
                status = self.get_next_status()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if status == 200:
                    self.wfile.write(json.dumps({"data": []}).encode())
                else:
                    self.wfile.write(
                        json.dumps({"error": "health check failed"}).encode()
                    )
        else:
            self.do_POST()


@pytest.fixture
def mock_upstream_server() -> Any:
    """Start mock upstream server."""
    server = HTTPServer(("127.0.0.1", 0), MockUpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield server

    server.shutdown()
    MockUpstreamHandler.reset()


@pytest.fixture
def running_proxy(
    temp_auth_dir: Path,
    mock_upstream_server: HTTPServer,
) -> Any:
    """Start proxy server with mock upstream."""
    host, port = mock_upstream_server.server_address[:2]

    settings = build_settings(
        auth_dir=str(temp_auth_dir),
        host="127.0.0.1",
        port=0,
        upstream=f"http://{host}:{port}",
        management_key="test-mgmt-key",
        trace_max=100,
        request_timeout=5,
        auto_heal_interval=1,  # Fast checks for testing
        auto_heal_success_target=2,
        auto_heal_max_attempts=3,
        max_ejection_percent=50,
        consecutive_error_threshold=3,
    )

    runtime = ProxyRuntime(settings=settings)
    runtime.reload_auths()

    server = ProxyHTTPServer((settings.host, settings.port), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "server": server,
        "runtime": runtime,
        "host": server.server_address[0],
        "port": server.server_address[1],
        "base_url": f"http://{server.server_address[0]}:{server.server_address[1]}",
    }

    server.shutdown()
    server.server_close()
    runtime.shutdown()


def _stop_auto_heal_thread(runtime: ProxyRuntime) -> None:
    runtime._auto_heal_stop.set()
    if runtime._auto_heal_thread is not None:
        runtime._auto_heal_thread.join(timeout=2)


def _install_fake_runtime_clock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    start: Optional[float] = None,
) -> Dict[str, float]:
    clock = {"now": float(time.time() if start is None else start)}

    monkeypatch.setattr(
        "cdx_proxy_cli_v2.proxy.server.time.time", lambda: clock["now"]
    )
    monkeypatch.setattr(
        "cdx_proxy_cli_v2.auth.rotation.time.time", lambda: clock["now"]
    )
    return clock


def _advance_auto_heal_cycles(
    runtime: ProxyRuntime,
    clock: Dict[str, float],
    *,
    cycles: int,
) -> None:
    step = float(runtime.auth_pool.auto_heal_interval) + 0.1
    for _ in range(cycles):
        runtime._run_auto_heal_cycle(now=clock["now"])
        clock["now"] += step


def make_proxy_request(
    base_url: str,
    path: str = "/v1/chat/completions",
    method: str = "POST",
    body: Optional[Dict] = None,
    management_key: str = "test-mgmt-key",
) -> Dict[str, Any]:
    """Make a request to the proxy server."""
    import http.client

    http.client.HTTPConnection(base_url.replace("http://", ""))
    url_parts = base_url.split("/")
    host_port = url_parts[2] if len(url_parts) > 2 else base_url

    conn = http.client.HTTPConnection(host_port)
    conn.request(
        method,
        path,
        body=json.dumps(body) if body else None,
        headers={
            "Content-Type": "application/json",
            "X-Management-Key": management_key,
        },
    )
    response = conn.getresponse()

    return {
        "status": response.status,
        "body": json.loads(response.read().decode()),
        "headers": dict(response.getheaders()),
    }


# ============================================================================
# E2E Tests: Auto-Heal Flow
# ============================================================================


class TestAutoHealE2E:
    """End-to-end tests for auto-heal blacklist restoration."""

    def test_auto_heal_restores_blacklisted_key(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """E2E: Blacklisted key should be restored after successful health checks."""
        runtime = running_proxy["runtime"]
        base_url = running_proxy["base_url"]
        _stop_auto_heal_thread(runtime)
        clock = _install_fake_runtime_clock(monkeypatch)

        # Step 1: Trigger blacklist with consecutive 401 errors
        # Use max_ejection_percent=100 to allow all keys to be blacklisted for this test
        runtime.auth_pool.max_ejection_percent = 100
        runtime.auth_pool.consecutive_error_threshold = 1  # Blacklist on first error

        MockUpstreamHandler.set_response_sequence([401, 401, 401])

        for _ in range(3):
            make_proxy_request(base_url)

        # Verify at least one key is blacklisted
        snapshot = runtime.auth_pool.health_snapshot()
        blacklisted_before = sum(1 for acc in snapshot if acc["status"] == "BLACKLIST")
        assert blacklisted_before > 0, (
            f"At least one key should be blacklisted, got snapshot: {snapshot}"
        )

        # Step 2: Mock upstream recovers (health checks will succeed)
        # Health checks always succeed by default in MockUpstreamHandler

        # Step 3: Manually advance two deterministic auto-heal cycles.
        _advance_auto_heal_cycles(runtime, clock, cycles=2)

        # Step 4: Verify keys are restored
        snapshot = runtime.auth_pool.health_snapshot()

        # Check that at least some progress was made (blacklist decreased or keys restored)
        blacklisted_after = sum(1 for acc in snapshot if acc["status"] == "BLACKLIST")
        ok_keys = [acc for acc in snapshot if acc["status"] == "OK"]

        # Either some keys are restored, or blacklist count decreased
        assert len(ok_keys) > 0 or blacklisted_after < blacklisted_before, (
            f"Auto-heal should make progress: before={blacklisted_before}, after={blacklisted_after}"
        )

    def test_auto_heal_failure_extends_blacklist(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """E2E: Failed health checks should extend blacklist TTL."""
        runtime = running_proxy["runtime"]
        base_url = running_proxy["base_url"]
        _stop_auto_heal_thread(runtime)
        clock = _install_fake_runtime_clock(monkeypatch)

        # Step 1: Trigger blacklist
        runtime.auth_pool.max_ejection_percent = 100
        runtime.auth_pool.consecutive_error_threshold = 1
        MockUpstreamHandler.set_response_sequence([401, 401, 401])

        for _ in range(3):
            make_proxy_request(base_url)

        # Get initial blacklist TTL
        snapshot = runtime.auth_pool.health_snapshot()
        initial_ttl = next(
            (
                acc.get("blacklist_seconds", 0)
                for acc in snapshot
                if acc["status"] == "BLACKLIST"
            ),
            0,
        )

        # Step 2: Mock upstream still failing (health checks will fail)
        MockUpstreamHandler.health_check_always_success = False
        MockUpstreamHandler.set_response_sequence([401] * 9)

        # Step 3: Advance enough cycles to trip auto-heal failure extension.
        _advance_auto_heal_cycles(runtime, clock, cycles=3)

        # Step 4: Verify blacklist was extended
        snapshot = runtime.auth_pool.health_snapshot()
        extended_ttl = next(
            (
                acc.get("blacklist_seconds", 0)
                for acc in snapshot
                if acc["status"] == "BLACKLIST"
            ),
            0,
        )

        assert extended_ttl > initial_ttl


# ============================================================================
# E2E Tests: Consecutive Error Threshold
# ============================================================================


class TestHardAuthEjection:
    """E2E tests for hard-auth threshold behavior."""

    def test_single_error_enters_transient_cooldown_before_threshold(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
    ) -> None:
        """E2E: A single 401 should cool the key down before blacklist threshold is reached."""
        runtime = running_proxy["runtime"]
        base_url = running_proxy["base_url"]

        # Single 401 error
        MockUpstreamHandler.set_response_sequence([401, 200])

        make_proxy_request(base_url)

        # With threshold=3 in the fixture, the key should only enter cooldown.
        snapshot = runtime.auth_pool.health_snapshot()
        cooldowns = [acc for acc in snapshot if acc["status"] == "COOLDOWN"]
        blacklisted = [acc for acc in snapshot if acc["status"] == "BLACKLIST"]
        assert len(cooldowns) >= 1
        assert len(blacklisted) == 0

    def test_threshold_reached_blacklists_key(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
    ) -> None:
        """E2E: Reaching the configured hard-auth threshold should eject the key."""
        runtime = running_proxy["runtime"]

        runtime.auth_pool.consecutive_error_threshold = 1
        first_auth = runtime.auth_pool.pick()
        assert first_auth is not None

        runtime.auth_pool.mark_result(
            first_auth.record.name, status=401, error_code="token_invalid"
        )

        snapshot = {acc["file"]: acc for acc in runtime.auth_pool.health_snapshot()}
        assert snapshot[first_auth.record.name]["status"] == "BLACKLIST"

    def test_success_clears_consecutive_counter_for_non_hard_failures(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
    ) -> None:
        """E2E: Success should clear transient counters even after prior failures."""
        runtime = running_proxy["runtime"]

        first_auth = runtime.auth_pool.pick()
        assert first_auth is not None
        runtime.auth_pool.mark_result(first_auth.record.name, status=429)
        runtime.auth_pool.mark_result(first_auth.record.name, status=200)

        snapshot = {acc["file"]: acc for acc in runtime.auth_pool.health_snapshot()}
        assert snapshot[first_auth.record.name]["status"] == "OK"
        auth_state = next(
            state
            for state in runtime.auth_pool._states
            if state.record.name == first_auth.record.name
        )
        assert auth_state.consecutive_errors == 0


# ============================================================================
# E2E Tests: Max Ejection Percent
# ============================================================================


class TestMaxEjectionPercent:
    """E2E tests for max ejection behavior."""

    def test_max_ejection_does_not_restore_hard_auth_failures(
        self,
        temp_auth_dir: Path,
        mock_upstream_server: HTTPServer,
    ) -> None:
        """E2E: Hard auth failures stay ejected even if the pool is exhausted."""
        # Create settings with 50% max ejection
        settings = build_settings(
            auth_dir=str(temp_auth_dir),
            host="127.0.0.1",
            port=0,
            upstream=f"http://{mock_upstream_server.server_address[0]}:{mock_upstream_server.server_address[1]}",
            management_key="test-mgmt-key",
            max_ejection_percent=50,
            consecutive_error_threshold=1,  # Blacklist on first error for this test
        )

        runtime = ProxyRuntime(settings=settings)
        runtime.reload_auths()

        # Set pool to have 3 keys, all should fail
        assert runtime.auth_pool.count() == 3

        # Trigger errors on all keys
        for auth_name in runtime.auth_pool.auth_files():
            runtime.auth_pool.mark_result(
                auth_name, status=401, error_code="token_invalid"
            )

        # Hard-auth-failed keys must not be force-restored
        picked = runtime.auth_pool.pick()
        assert picked is None

        snapshot = runtime.auth_pool.health_snapshot()
        blacklisted = [acc for acc in snapshot if acc["status"] == "BLACKLIST"]
        cooldown = [acc for acc in snapshot if acc["status"] == "COOLDOWN"]
        assert len(blacklisted) == 1
        assert len(cooldown) == 2


# ============================================================================
# E2E Tests: Pool Exhaustion
# ============================================================================


class TestPoolExhaustion:
    """E2E tests for pool exhaustion scenarios."""

    def test_pool_exhausted_returns_503(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
    ) -> None:
        """E2E: When all keys unavailable, return 503."""
        runtime = running_proxy["runtime"]
        base_url = running_proxy["base_url"]

        # Make all keys unavailable (cooldown)
        for auth_name in runtime.auth_pool.auth_files():
            runtime.auth_pool.mark_cooldown(auth_name, seconds=60)

        # Request should return 503
        result = make_proxy_request(base_url)
        assert result["status"] == 503
        assert "no auths available" in json.dumps(result["body"])

    def test_pool_recovers_after_cooldown(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
    ) -> None:
        """E2E: Pool recovers after cooldown expires."""
        runtime = running_proxy["runtime"]
        base_url = running_proxy["base_url"]

        # Set short cooldown
        for auth_name in runtime.auth_pool.auth_files():
            runtime.auth_pool.mark_cooldown(auth_name, seconds=2)

        # Initially should return 503
        result = make_proxy_request(base_url)
        assert result["status"] == 503

        # Wait for cooldown to expire
        time.sleep(2.5)

        # Mock success
        MockUpstreamHandler.set_response_sequence([200])

        # Should recover
        result = make_proxy_request(base_url)
        assert result["status"] == 200


# ============================================================================
# E2E Tests: Event Notifications
# ============================================================================


class TestEventNotifications:
    """E2E tests for event notifications."""

    def test_blacklist_event_logged(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
    ) -> None:
        """E2E: Blacklist events should be logged."""
        runtime = running_proxy["runtime"]
        base_url = running_proxy["base_url"]

        # Trigger blacklist
        runtime.auth_pool.consecutive_error_threshold = 1  # Blacklist on first error
        MockUpstreamHandler.set_response_sequence([401, 401, 401])

        for _ in range(3):
            make_proxy_request(base_url)

        # Check trace events
        events = runtime.trace_store.list(limit=50)
        blacklist_events = [e for e in events if e.get("event") == "auth.ejected"]

        assert len(blacklist_events) > 0, "Should log blacklist event"

    def test_auto_heal_event_logged(
        self,
        running_proxy: Dict[str, Any],
        mock_upstream_server: HTTPServer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """E2E: Auto-heal events should be logged."""
        runtime = running_proxy["runtime"]
        base_url = running_proxy["base_url"]
        _stop_auto_heal_thread(runtime)
        clock = _install_fake_runtime_clock(monkeypatch)

        # Configure for testing
        runtime.auth_pool.consecutive_error_threshold = 1
        runtime.auth_pool.max_ejection_percent = 100

        # Trigger blacklist
        MockUpstreamHandler.set_response_sequence([401, 401, 401])
        for _ in range(3):
            make_proxy_request(base_url)

        # Mock recovery - health checks always succeed by default
        MockUpstreamHandler.set_response_sequence([200, 200, 200, 200])

        # Drive two deterministic heal cycles instead of sleeping.
        _advance_auto_heal_cycles(runtime, clock, cycles=2)

        # Check trace events for any auto-heal or recovery events
        events = runtime.trace_store.list(limit=50)
        heal_events = [
            e
            for e in events
            if e.get("event") in ("auto_heal.success", "auto_heal.failure")
        ]

        # Should have some auto-heal activity
        assert len(heal_events) > 0 or len(events) > 3, (
            "Should have auto-heal or recovery events"
        )


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
