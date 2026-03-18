"""Comprehensive tests for config settings module."""

from __future__ import annotations

from pathlib import Path

import pytest

from cdx_proxy_cli_v2.config.settings import (
    ENV_AUTO_RESET_COOLDOWN,
    ENV_AUTO_RESET_ON_SINGLE_KEY,
    ENV_AUTO_RESET_STREAK,
    ENV_COMPACT_TIMEOUT,
    ENV_ENV_FILE,
    ENV_HOST,
    ENV_LIMIT_MIN_REMAINING_PERCENT,
    ENV_MAX_IN_FLIGHT_REQUESTS,
    ENV_MAX_PENDING_REQUESTS,
    ENV_PORT,
    ENV_REQUEST_TIMEOUT,
    ENV_TRACE_MAX,
    ENV_UPSTREAM,
    DEFAULT_AUTO_RESET_COOLDOWN,
    DEFAULT_AUTO_RESET_STREAK,
    DEFAULT_LIMIT_MIN_REMAINING_PERCENT,
    DEFAULT_UPSTREAM,
    Settings,
    build_settings,
    load_env_file,
    parse_bool,
    parse_port,
    parse_positive_int,
    format_shell_exports,
    resolve_path,
    upsert_env_values,
)


# ============================================================================
# Test: resolve_path
# ============================================================================


class TestResolvePath:
    """Tests for resolve_path function."""

    def test_expands_home_directory(self):
        """Should expand ~ to user's home directory."""
        result = resolve_path("~/test/path")
        expected = Path.home() / "test" / "path"
        assert result == expected

    def test_handles_relative_path(self):
        """Should return Path object for relative paths."""
        result = resolve_path("relative/path")
        assert isinstance(result, Path)
        assert "relative/path" in str(result)

    def test_handles_absolute_path(self):
        """Should return Path object for absolute paths."""
        result = resolve_path("/absolute/path")
        assert isinstance(result, Path)
        assert result.is_absolute()


# ============================================================================
# Test: parse_bool
# ============================================================================


class TestParseBool:
    """Tests for parse_bool function."""

    @pytest.mark.parametrize(
        "value", ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"]
    )
    def test_returns_true_for_truthy_values(self, value: str):
        """Should return True for truthy string values."""
        assert parse_bool(value) is True

    @pytest.mark.parametrize(
        "value",
        ["0", "false", "False", "FALSE", "no", "NO", "off", "OFF", "", "random"],
    )
    def test_returns_false_for_falsy_values(self, value: str):
        """Should return False for non-truthy string values."""
        assert parse_bool(value) is False

    def test_returns_default_for_none(self):
        """Should return default when value is None."""
        assert parse_bool(None, default=True) is True
        assert parse_bool(None, default=False) is False


# ============================================================================
# Test: parse_port
# ============================================================================


class TestParsePort:
    """Tests for parse_port function."""

    def test_accepts_valid_port(self):
        """Should parse valid port numbers."""
        assert parse_port("8080", default=0) == 8080
        assert parse_port("443", default=0) == 443
        assert parse_port("1", default=0) == 1
        assert parse_port("65535", default=0) == 65535

    def test_returns_default_for_invalid_port(self):
        """Should return default for invalid port numbers."""
        assert parse_port("-1", default=0) == 0
        assert parse_port("65536", default=0) == 0  # Too high
        assert parse_port("abc", default=0) == 0
        assert parse_port("", default=0) == 0
        assert parse_port(None, default=0) == 0

    def test_accepts_zero_for_auto_assign(self):
        """Should accept 0 for auto port assignment."""
        assert parse_port("0", default=8080) == 0


# ============================================================================
# Test: parse_positive_int
# ============================================================================


class TestParsePositiveInt:
    """Tests for parse_positive_int function."""

    def test_accepts_positive_integers(self):
        """Should parse positive integers."""
        assert parse_positive_int("100", default=10) == 100
        assert parse_positive_int("1", default=10) == 1

    def test_returns_default_for_non_positive(self):
        """Should return default for zero or negative values."""
        assert parse_positive_int("0", default=10) == 10
        assert parse_positive_int("-5", default=10) == 10

    def test_returns_default_for_invalid_input(self):
        """Should return default for invalid input."""
        assert parse_positive_int("abc", default=10) == 10
        assert parse_positive_int(None, default=10) == 10


# ============================================================================
# Test: load_env_file
# ============================================================================


class TestLoadEnvFile:
    """Tests for load_env_file function."""

    def test_loads_simple_key_value(self, tmp_path: Path):
        """Should load simple KEY=value pairs."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY=test_value\n")

        result = load_env_file(env_file)
        assert result == {"TEST_KEY": "test_value"}

    def test_handles_quoted_values(self, tmp_path: Path):
        """Should strip quotes from values."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=\"double quoted\"\nKEY2='single quoted'\n")

        result = load_env_file(env_file)
        assert result["KEY1"] == "double quoted"
        assert result["KEY2"] == "single quoted"

    def test_ignores_comments(self, tmp_path: Path):
        """Should ignore comment lines."""
        env_file = tmp_path / ".env"
        env_file.write_text("# This is a comment\nKEY=value\n# Another comment\n")

        result = load_env_file(env_file)
        assert result == {"KEY": "value"}

    def test_handles_export_prefix(self, tmp_path: Path):
        """Should handle 'export KEY=value' format."""
        env_file = tmp_path / ".env"
        env_file.write_text("export KEY=value\n")

        result = load_env_file(env_file)
        assert result == {"KEY": "value"}

    def test_ignores_lines_without_equals(self, tmp_path: Path):
        """Should ignore lines without = sign."""
        env_file = tmp_path / ".env"
        env_file.write_text("INVALID_LINE\nKEY=value\n")

        result = load_env_file(env_file)
        assert result == {"KEY": "value"}

    def test_returns_empty_for_missing_file(self, tmp_path: Path):
        """Should return empty dict for missing file."""
        result = load_env_file(tmp_path / "nonexistent.env")
        assert result == {}


# ============================================================================
# Test: upsert_env_values
# ============================================================================


class TestUpsertEnvValues:
    """Tests for upsert_env_values function."""

    def test_creates_new_file(self, tmp_path: Path):
        """Should create env file if it doesn't exist."""
        env_file = tmp_path / ".env"

        result = upsert_env_values(env_file, {"KEY": "value"})

        assert result is True
        assert env_file.exists()
        assert load_env_file(env_file) == {"KEY": "value"}

    def test_updates_existing_values(self, tmp_path: Path):
        """Should update existing values."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=old_value\n")

        result = upsert_env_values(env_file, {"KEY": "new_value"})

        assert result is True
        assert load_env_file(env_file) == {"KEY": "new_value"}

    def test_returns_false_if_no_changes(self, tmp_path: Path):
        """Should return False if values unchanged."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=value\n")

        result = upsert_env_values(env_file, {"KEY": "value"})

        assert result is False

    def test_adds_new_values(self, tmp_path: Path):
        """Should add new values while keeping existing."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\n")

        result = upsert_env_values(env_file, {"KEY2": "value2"})

        assert result is True
        loaded = load_env_file(env_file)
        assert loaded["KEY1"] == "value1"
        assert loaded["KEY2"] == "value2"


# ============================================================================
# Test: Settings dataclass
# ============================================================================


class TestSettings:
    """Tests for Settings dataclass."""

    def test_base_url_property(self):
        """Should construct base_url from host and port."""
        settings = Settings(
            auth_dir="/tmp/auths",
            host="127.0.0.1",
            port=8080,
            upstream="https://api.example.com",
            management_key="key",
            allow_non_loopback=False,
            trace_max=100,
            request_timeout=45,
            compact_timeout=120,
        )

        assert settings.base_url == "http://127.0.0.1:8080"

    def test_with_port_returns_new_instance(self):
        """with_port should return new Settings with updated port."""
        original = Settings(
            auth_dir="/tmp",
            host="127.0.0.1",
            port=8080,
            upstream="https://api.example.com",
            management_key=None,
            allow_non_loopback=False,
            trace_max=100,
            request_timeout=45,
            compact_timeout=120,
        )

        updated = original.with_port(9000)

        assert original.port == 8080  # Original unchanged
        assert updated.port == 9000

    def test_with_management_key_returns_new_instance(self):
        """with_management_key should return new Settings with updated key."""
        original = Settings(
            auth_dir="/tmp",
            host="127.0.0.1",
            port=8080,
            upstream="https://api.example.com",
            management_key=None,
            allow_non_loopback=False,
            trace_max=100,
            request_timeout=45,
            compact_timeout=120,
        )

        updated = original.with_management_key("new-key")

        assert original.management_key is None
        assert updated.management_key == "new-key"


# ============================================================================
# Test: build_settings precedence
# ============================================================================


class TestBuildSettingsPrecedence:
    """Tests for build_settings precedence rules."""

    def test_cli_args_override_env_vars(self, tmp_path: Path, monkeypatch):
        """CLI args should take precedence over env vars."""
        monkeypatch.setenv(ENV_HOST, "env-host")

        settings = build_settings(
            auth_dir=str(tmp_path),
            host="cli-host",
        )

        assert settings.host == "cli-host"

    def test_whitespace_stripped_from_values(self):
        """Should strip whitespace from string values."""
        settings = build_settings(
            auth_dir="/tmp",
            host="  127.0.0.1  ",
            upstream="  https://api.example.com  ",
        )

        assert settings.host == "127.0.0.1"
        assert settings.upstream == "https://api.example.com"

    def test_chatgpt_upstream_without_backend_path_is_normalized(self):
        """Bare ChatGPT upstreams should route to /backend-api automatically."""
        settings = build_settings(
            auth_dir="/tmp",
            upstream="https://chatgpt.com",
        )

        assert settings.upstream == DEFAULT_UPSTREAM

    def test_chatgpt_upstream_from_env_without_backend_path_is_normalized(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setenv(ENV_UPSTREAM, "https://chat.openai.com/")

        settings = build_settings(auth_dir=str(tmp_path))

        assert settings.upstream == "https://chat.openai.com/backend-api"

    def test_explicit_auth_dir_ignores_inherited_env_file(self, tmp_path: Path, monkeypatch):
        inherited_env = tmp_path / "inherited.env"
        inherited_env.write_text("CLIPROXY_MANAGEMENT_KEY=inherited-key\n", encoding="utf-8")
        monkeypatch.setenv(ENV_ENV_FILE, str(inherited_env))

        auth_dir = tmp_path / "auths"
        auth_dir.mkdir()
        settings = build_settings(auth_dir=str(auth_dir))

        assert settings.env_path == auth_dir / ".env"

    def test_inherited_env_file_is_used_without_explicit_auth_dir(
        self, tmp_path: Path, monkeypatch
    ):
        inherited_env = tmp_path / "inherited.env"
        inherited_env.write_text("CLIPROXY_MANAGEMENT_KEY=inherited-key\n", encoding="utf-8")
        monkeypatch.setenv(ENV_ENV_FILE, str(inherited_env))

        settings = build_settings()

        assert settings.env_path == inherited_env


class TestBuildSettingsNumericResolution:
    """Tests for numeric resolution precedence and clamping."""

    def test_port_cli_override_takes_precedence(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv(ENV_PORT, "8080")

        settings = build_settings(auth_dir=str(tmp_path), port=9000)

        assert settings.port == 9000

    def test_port_cli_override_clamps_to_zero(self, tmp_path: Path):
        settings = build_settings(auth_dir=str(tmp_path), port=-5)

        assert settings.port == 0

    def test_numeric_settings_fall_back_to_env(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv(ENV_TRACE_MAX, "700")
        monkeypatch.setenv(ENV_REQUEST_TIMEOUT, "60")
        monkeypatch.setenv(ENV_COMPACT_TIMEOUT, "180")
        monkeypatch.setenv(ENV_LIMIT_MIN_REMAINING_PERCENT, "7.5")
        monkeypatch.setenv(ENV_MAX_IN_FLIGHT_REQUESTS, "21")
        monkeypatch.setenv(ENV_MAX_PENDING_REQUESTS, "4")
        monkeypatch.setenv(ENV_AUTO_RESET_STREAK, "9")
        monkeypatch.setenv(ENV_AUTO_RESET_COOLDOWN, "240")

        settings = build_settings(auth_dir=str(tmp_path))

        assert settings.trace_max == 700
        assert settings.request_timeout == 60
        assert settings.compact_timeout == 180
        assert settings.limit_min_remaining_percent == 7.5
        assert settings.max_in_flight_requests == 21
        assert settings.max_pending_requests == 4
        assert settings.auto_reset_streak == 9
        assert settings.auto_reset_cooldown == 240

    def test_numeric_cli_overrides_clamp_minimum(self, tmp_path: Path):
        settings = build_settings(
            auth_dir=str(tmp_path),
            trace_max=0,
            request_timeout=-10,
            compact_timeout=0,
            limit_min_remaining_percent=-1,
            max_in_flight_requests=-3,
            max_pending_requests=-1,
            auto_reset_streak=0,
            auto_reset_cooldown=-5,
        )

        assert settings.trace_max == 1
        assert settings.request_timeout == 1
        assert settings.compact_timeout == 1
        assert settings.limit_min_remaining_percent == 0.0
        assert settings.max_in_flight_requests == 0
        assert settings.max_pending_requests == 0
        assert settings.auto_reset_streak == 1
        assert settings.auto_reset_cooldown == 1

    def test_limit_min_remaining_percent_defaults_safely(self, tmp_path: Path):
        settings = build_settings(auth_dir=str(tmp_path))

        assert (
            settings.limit_min_remaining_percent
            == DEFAULT_LIMIT_MIN_REMAINING_PERCENT
        )


class TestBuildSettingsAutoReset:
    """Tests for one-key starvation recovery settings."""

    def test_auto_reset_defaults_are_safe(self, tmp_path: Path):
        settings = build_settings(auth_dir=str(tmp_path))

        assert settings.auto_reset_on_single_key is False
        assert settings.auto_reset_streak == DEFAULT_AUTO_RESET_STREAK
        assert settings.auto_reset_cooldown == DEFAULT_AUTO_RESET_COOLDOWN

    def test_auto_reset_bool_falls_back_to_env(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv(ENV_AUTO_RESET_ON_SINGLE_KEY, "true")

        settings = build_settings(auth_dir=str(tmp_path))

        assert settings.auto_reset_on_single_key is True

    def test_auto_reset_cli_bool_overrides_env(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv(ENV_AUTO_RESET_ON_SINGLE_KEY, "true")

        settings = build_settings(
            auth_dir=str(tmp_path),
            auto_reset_on_single_key=False,
        )

        assert settings.auto_reset_on_single_key is False


# ============================================================================
# Test: format_shell_exports
# ============================================================================


class TestFormatShellExports:
    """Tests for format_shell_exports function."""

    def test_formats_simple_values(self):
        """Should format simple key=value pairs."""
        result = format_shell_exports({"KEY": "value"})

        assert "export KEY='value'" in result

    def test_sorts_keys_alphabetically(self):
        """Should sort keys alphabetically."""
        result = format_shell_exports({"Z_KEY": "z", "A_KEY": "a"})

        lines = result.split("\n")
        assert lines[0] == "export A_KEY='a'"
        assert lines[1] == "export Z_KEY='z'"

    def test_escapes_single_quotes(self):
        """Should escape single quotes in values."""
        result = format_shell_exports({"KEY": "value'with'quotes"})

        # Should contain escaped quotes
        assert "'" in result
        assert "value'with'quotes" not in result  # Raw quotes not present

    def test_handles_multiple_values(self):
        """Should handle multiple key-value pairs."""
        result = format_shell_exports(
            {
                "KEY1": "value1",
                "KEY2": "value2",
            }
        )

        assert "KEY1" in result
        assert "KEY2" in result


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
