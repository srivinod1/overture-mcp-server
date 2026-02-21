"""
Integration tests for authentication configuration.

Tests that auth is properly configured based on transport and API key settings.
Verifies the auth verifier is created or skipped correctly.

Most tests don't require fastmcp — they test the auth module directly.
"""

import pytest
from overture_mcp.auth import create_auth_verifier, HAS_FASTMCP_AUTH
from overture_mcp.config import ServerConfig, load_config


class TestAuthVerifierCreation:
    """Tests for create_auth_verifier function."""

    def test_empty_key_returns_none(self):
        """No API key should return None (no auth)."""
        result = create_auth_verifier("")
        assert result is None

    def test_none_equivalent_returns_none(self):
        """Empty string API key should return None."""
        result = create_auth_verifier("")
        assert result is None

    @pytest.mark.skipif(not HAS_FASTMCP_AUTH, reason="fastmcp auth not available")
    def test_valid_key_returns_verifier(self):
        """Valid API key should return a token verifier."""
        result = create_auth_verifier("test-key-12345")
        assert result is not None

    @pytest.mark.skipif(not HAS_FASTMCP_AUTH, reason="fastmcp auth not available")
    def test_verifier_type(self):
        """Verifier should be a StaticTokenVerifier."""
        from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
        result = create_auth_verifier("test-key-12345")
        assert isinstance(result, StaticTokenVerifier)


class TestTransportAuthRequirements:
    """Tests for transport-specific auth requirements."""

    def test_stdio_no_key_ok(self, monkeypatch):
        """stdio transport should work without an API key."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.delenv("TRANSPORT", raising=False)
        config = load_config()
        assert config.api_key == ""

    def test_sse_requires_key(self, monkeypatch):
        """SSE transport requires an API key."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.setenv("TRANSPORT", "sse")
        with pytest.raises(ValueError, match="OVERTURE_API_KEY"):
            load_config()

    def test_http_requires_key(self, monkeypatch):
        """HTTP transport requires an API key."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.setenv("TRANSPORT", "http")
        with pytest.raises(ValueError, match="OVERTURE_API_KEY"):
            load_config()

    def test_sse_with_key_ok(self, monkeypatch):
        """SSE transport with API key should succeed."""
        monkeypatch.setenv("OVERTURE_API_KEY", "my-key")
        monkeypatch.setenv("TRANSPORT", "sse")
        config = load_config()
        assert config.api_key == "my-key"

    def test_http_with_key_ok(self, monkeypatch):
        """HTTP transport with API key should succeed."""
        monkeypatch.setenv("OVERTURE_API_KEY", "my-key")
        monkeypatch.setenv("TRANSPORT", "http")
        config = load_config()
        assert config.api_key == "my-key"


class TestServerConfigAuth:
    """Tests for auth-related ServerConfig behavior."""

    def test_config_stores_api_key(self):
        config = ServerConfig(api_key="test-key")
        assert config.api_key == "test-key"

    def test_config_empty_api_key_allowed(self):
        """Empty key is allowed at the config level (enforced at load_config)."""
        config = ServerConfig(api_key="")
        assert config.api_key == ""

    def test_config_frozen(self):
        """API key should not be modifiable after creation."""
        config = ServerConfig(api_key="test-key")
        with pytest.raises(AttributeError):
            config.api_key = "new-key"
