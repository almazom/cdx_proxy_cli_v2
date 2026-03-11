"""Tests for auto-heal blacklist functionality."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch


from cdx_proxy_cli_v2.auth.models import AuthRecord, AuthState
from cdx_proxy_cli_v2.auth.rotation import DEFAULT_BLACKLIST_SECONDS, RoundRobinAuthPool
from cdx_proxy_cli_v2.config.settings import Settings
from cdx_proxy_cli_v2.proxy.server import ProxyRuntime


# Test configuration values (defaults from Settings)
AUTO_HEAL_CHECK_INTERVAL_SECONDS = 60
AUTO_HEAL_SUCCESS_TARGET = 2
AUTO_HEAL_MAX_ATTEMPTS = 3


class TestAutoHealTracking:
    """Tests for auto-heal state tracking in AuthState."""

    def test_auth_state_has_auto_heal_fields(self) -> None:
        """AuthState should have auto-heal tracking fields."""
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        state = AuthState(record=record)

        assert state.auto_heal_successes == 0
        assert state.auto_heal_target == 2
        assert state.auto_heal_failures == 0
        assert state.auto_heal_last_check == 0.0


class TestAutoHealSuccess:
    """Tests for successful auto-heal restoration."""

    def test_mark_success_restores_blacklisted_key(self) -> None:
        """Successful health check should restore blacklisted key after target successes."""
        pool = RoundRobinAuthPool(
            consecutive_error_threshold=1
        )  # Blacklist on first error
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        pool.load([record])

        # Mark as blacklisted
        time.time()
        pool.mark_result("test.json", status=401, error_code="token_invalid")

        # Verify blacklisted
        snapshot = pool.health_snapshot()
        assert snapshot[0]["status"] == "BLACKLIST"

        # Simulate successful health checks
        pool.mark_result("test.json", status=200)
        pool.mark_result("test.json", status=200)

        # Should be restored
        snapshot = pool.health_snapshot()
        assert snapshot[0]["status"] == "OK"
        assert snapshot[0].get("blacklist_seconds") is None

    def test_mark_success_tracks_auto_heal_progress(self) -> None:
        """Auto-heal successes should be tracked."""
        pool = RoundRobinAuthPool(
            consecutive_error_threshold=1
        )  # Blacklist on first error
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        pool.load([record])

        # Mark as blacklisted
        pool.mark_result("test.json", status=401)

        # First success
        pool.mark_result("test.json", status=200)

        # Check internal state
        state = pool._states[0]
        assert state.auto_heal_successes == 1
        assert state.auto_heal_failures == 0


class TestAutoHealFailure:
    """Tests for failed auto-heal attempts."""

    def test_mark_auto_heal_failure_tracks_failures(self) -> None:
        """Failed health checks should be tracked."""
        pool = RoundRobinAuthPool(
            consecutive_error_threshold=1
        )  # Blacklist on first error
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        pool.load([record])

        # Mark as blacklisted
        pool.mark_result("test.json", status=401)

        now = time.time()
        pool.mark_auto_heal_failure("test.json", now)

        state = pool._states[0]
        assert state.auto_heal_failures == 1
        assert state.auto_heal_successes == 0
        assert state.auto_heal_last_check == now

    def test_mark_auto_heal_failure_resets_successes(self) -> None:
        """Failure should reset success counter."""
        pool = RoundRobinAuthPool(
            consecutive_error_threshold=1
        )  # Blacklist on first error
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        pool.load([record])

        # Mark as blacklisted, then simulate success
        pool.mark_result("test.json", status=401)
        pool.mark_result("test.json", status=200)

        state = pool._states[0]
        assert state.auto_heal_successes >= 1

        # Now fail
        now = time.time()
        pool.mark_auto_heal_failure("test.json", now)

        assert state.auto_heal_successes == 0

    def test_mark_auto_heal_failure_extends_blacklist(self) -> None:
        """Multiple failures should extend blacklist TTL."""
        pool = RoundRobinAuthPool(
            consecutive_error_threshold=1
        )  # Blacklist on first error
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        pool.load([record])

        # Mark as blacklisted
        pool.mark_result("test.json", status=401)

        now = time.time()
        initial_blacklist_until = pool._states[0].blacklist_until

        # Simulate max failures
        for _ in range(AUTO_HEAL_MAX_ATTEMPTS):
            pool.mark_auto_heal_failure("test.json", now)

        # Blacklist should be extended
        state = pool._states[0]
        assert state.blacklist_until >= initial_blacklist_until
        assert state.auto_heal_failures == 0  # Reset after max


class TestAutoHealProbeTransport:
    """Tests for the runtime auto-heal probe transport."""

    def test_perform_auto_heal_check_supports_http_upstream(self, tmp_path) -> None:
        auth_dir = tmp_path / "auths"
        auth_dir.mkdir()
        (auth_dir / "test.json").write_text(
            '{"access_token": "tok-1", "email": "test@example.com"}',
            encoding="utf-8",
        )
        runtime = ProxyRuntime(
            settings=Settings(
                auth_dir=str(auth_dir),
                host="127.0.0.1",
                port=0,
                upstream="http://127.0.0.1:8080",
                management_key="test-mgmt",
                allow_non_loopback=False,
                trace_max=10,
                request_timeout=5,
                compact_timeout=5,
                auto_heal_interval=60,
                auto_heal_success_target=2,
                auto_heal_max_attempts=3,
                max_ejection_percent=50,
                consecutive_error_threshold=1,
            )
        )
        mock_connection = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_connection.getresponse.return_value = mock_response

        try:
            with patch("http.client.HTTPConnection", return_value=mock_connection):
                assert runtime._perform_auto_heal_check({"file": "test.json"}) is True
        finally:
            runtime.shutdown()


class TestAutoHealProbationCycle:
    """Tests for probation recovery without foreground traffic."""

    def test_auto_heal_cycle_probes_probation_keys(self, tmp_path, monkeypatch) -> None:
        now = 5000.0
        monkeypatch.setattr("cdx_proxy_cli_v2.auth.rotation.time.time", lambda: now)
        monkeypatch.setattr("cdx_proxy_cli_v2.proxy.server.time.time", lambda: now)

        auth_dir = tmp_path / "auths"
        auth_dir.mkdir()
        settings = Settings(
            auth_dir=str(auth_dir),
            host="127.0.0.1",
            port=0,
            upstream="https://chatgpt.com/backend-api",
            management_key="test-mgmt",
            allow_non_loopback=False,
            trace_max=10,
            request_timeout=5,
            compact_timeout=5,
            auto_heal_interval=1,
            auto_heal_success_target=2,
            auto_heal_max_attempts=3,
            max_ejection_percent=50,
            consecutive_error_threshold=1,
        )

        with patch.object(ProxyRuntime, "_start_auto_heal_checker", lambda self: None):
            runtime = ProxyRuntime(settings=settings)

        (auth_dir / "a.json").write_text(
            json.dumps(
                {
                    "access_token": "tok-a",
                    "email": "a@example.com",
                    "tokens": {"account_id": "acc-a"},
                }
            ),
            encoding="utf-8",
        )
        (auth_dir / "b.json").write_text(
            json.dumps(
                {
                    "access_token": "tok-b",
                    "email": "b@example.com",
                    "tokens": {"account_id": "acc-b"},
                }
            ),
            encoding="utf-8",
        )
        runtime.reload_auths()

        try:
            runtime.auth_pool.mark_result(
                "a.json", status=401, error_code="token_invalid"
            )

            now = now + float(DEFAULT_BLACKLIST_SECONDS) + 1.0
            snapshot = {
                item["file"]: item for item in runtime.auth_pool.health_snapshot()
            }
            assert snapshot["a.json"]["status"] == "PROBATION"

            runtime._perform_auto_heal_check = MagicMock(return_value=True)

            runtime._run_auto_heal_cycle(now=now)
            now = now + 2.0
            runtime._run_auto_heal_cycle(now=now)

            snapshot = {
                item["file"]: item for item in runtime.auth_pool.health_snapshot()
            }
            assert snapshot["a.json"]["status"] == "OK"
            assert snapshot["a.json"]["eligible_now"] is True
        finally:
            runtime.shutdown()


class TestAutoHealConfiguration:
    """Tests for auto-heal configuration constants."""

    def test_auto_heal_constants_defined(self) -> None:
        """Auto-heal constants should be defined."""
        assert AUTO_HEAL_CHECK_INTERVAL_SECONDS > 0
        assert AUTO_HEAL_SUCCESS_TARGET > 0
        assert AUTO_HEAL_MAX_ATTEMPTS > 0

        # Reasonable defaults
        assert AUTO_HEAL_CHECK_INTERVAL_SECONDS == 60
        assert AUTO_HEAL_SUCCESS_TARGET == 2
        assert AUTO_HEAL_MAX_ATTEMPTS == 3


class TestAuthStateAvailable:
    """Tests for AuthState.available() with auto-heal fields."""

    def test_available_respects_blacklist(self) -> None:
        """Key should not be available while blacklisted."""
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        state = AuthState(record=record)

        now = time.time()
        state.blacklist_until = now + 100  # 100 seconds in future

        assert state.available(now) is False

    def test_available_after_blacklist_expires(self) -> None:
        """Key should be available after blacklist expires."""
        record = AuthRecord(name="test.json", path="/tmp/test.json", token="tok-1")
        state = AuthState(record=record)

        now = time.time()
        state.blacklist_until = now - 100  # 100 seconds in past

        assert state.available(now) is True
