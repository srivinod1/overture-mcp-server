"""Unit tests for config module."""

import os
import pytest
from overture_mcp.config import (
    ServerConfig,
    load_config,
    DEFAULT_TOOL_MODE,
    DEFAULT_DATA_VERSION,
    DEFAULT_MAX_CONCURRENT_QUERIES,
    DEFAULT_MAX_RADIUS_M,
    S3_BUCKET,
)


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_default_tool_mode(self):
        config = ServerConfig(api_key="test")
        assert config.tool_mode == "direct"

    def test_tool_mode_progressive(self):
        config = ServerConfig(api_key="test", tool_mode="progressive")
        assert config.tool_mode == "progressive"

    def test_tool_mode_invalid(self):
        with pytest.raises(ValueError, match="Invalid TOOL_MODE"):
            ServerConfig(api_key="test", tool_mode="invalid")

    def test_default_data_version(self):
        config = ServerConfig(api_key="test")
        assert config.data_version == DEFAULT_DATA_VERSION

    def test_data_version_override(self):
        config = ServerConfig(api_key="test", data_version="2026-04-21.0")
        assert config.data_version == "2026-04-21.0"

    def test_default_max_concurrent(self):
        config = ServerConfig(api_key="test")
        assert config.max_concurrent_queries == DEFAULT_MAX_CONCURRENT_QUERIES

    def test_default_max_radius(self):
        config = ServerConfig(api_key="test")
        assert config.max_radius_m == DEFAULT_MAX_RADIUS_M

    def test_max_concurrent_below_one(self):
        with pytest.raises(ValueError, match="MAX_CONCURRENT_QUERIES must be >= 1"):
            ServerConfig(api_key="test", max_concurrent_queries=0)

    def test_max_radius_below_one(self):
        with pytest.raises(ValueError, match="MAX_RADIUS_M must be >= 1"):
            ServerConfig(api_key="test", max_radius_m=0)

    def test_config_is_frozen(self):
        config = ServerConfig(api_key="test")
        with pytest.raises(AttributeError):
            config.api_key = "changed"


class TestS3Paths:
    """Tests for S3 path construction."""

    def test_s3_path_construction(self):
        config = ServerConfig(api_key="test", data_version="2026-01-21.0")
        path = config.s3_path("places", "place")
        assert path == f"s3://{S3_BUCKET}/release/2026-01-21.0/theme=places/type=place/*"

    def test_places_path(self):
        config = ServerConfig(api_key="test")
        assert "theme=places/type=place" in config.places_path

    def test_buildings_path(self):
        config = ServerConfig(api_key="test")
        assert "theme=buildings/type=building" in config.buildings_path

    def test_divisions_path(self):
        config = ServerConfig(api_key="test")
        assert "theme=divisions/type=division_area" in config.divisions_path

    def test_version_in_path(self):
        config = ServerConfig(api_key="test", data_version="2026-04-21.0")
        assert "2026-04-21.0" in config.places_path


class TestLoadConfig:
    """Tests for load_config function."""

    def test_missing_api_key_sse_transport(self, monkeypatch):
        """API key is required for SSE transport."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.setenv("TRANSPORT", "sse")
        with pytest.raises(ValueError, match="OVERTURE_API_KEY"):
            load_config()

    def test_empty_api_key_http_transport(self, monkeypatch):
        """Empty API key is rejected for HTTP transport."""
        monkeypatch.setenv("OVERTURE_API_KEY", "")
        monkeypatch.setenv("TRANSPORT", "http")
        with pytest.raises(ValueError, match="OVERTURE_API_KEY"):
            load_config()

    def test_missing_api_key_stdio_ok(self, monkeypatch):
        """API key is optional for stdio transport (local only)."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.delenv("TRANSPORT", raising=False)
        config = load_config()
        assert config.api_key == ""

    def test_missing_api_key_stdio_explicit(self, monkeypatch):
        """Explicit stdio transport allows missing API key."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.setenv("TRANSPORT", "stdio")
        config = load_config()
        assert config.api_key == ""

    def test_valid_api_key(self, monkeypatch):
        monkeypatch.setenv("OVERTURE_API_KEY", "my-secret-key")
        config = load_config()
        assert config.api_key == "my-secret-key"

    def test_tool_mode_from_env(self, monkeypatch):
        monkeypatch.setenv("OVERTURE_API_KEY", "key")
        monkeypatch.setenv("TOOL_MODE", "progressive")
        config = load_config()
        assert config.tool_mode == "progressive"

    def test_data_version_from_env(self, monkeypatch):
        monkeypatch.setenv("OVERTURE_API_KEY", "key")
        monkeypatch.setenv("OVERTURE_DATA_VERSION", "2026-04-21.0")
        config = load_config()
        assert config.data_version == "2026-04-21.0"
