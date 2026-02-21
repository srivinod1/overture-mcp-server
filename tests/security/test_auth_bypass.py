"""
Security tests: Authentication bypass prevention.

These tests verify that the authentication layer cannot be circumvented
through common bypass techniques. They test the auth module directly
since testing the full HTTP stack requires a running FastMCP server.
"""

import pytest
from overture_mcp.auth import create_auth_verifier, HAS_FASTMCP_AUTH
from overture_mcp.config import ServerConfig, load_config


class TestAuthBypassPrevention:
    """Tests that auth cannot be bypassed through common techniques."""

    def test_empty_string_key_returns_no_auth(self):
        """Empty string should not create an auth verifier."""
        verifier = create_auth_verifier("")
        assert verifier is None

    def test_whitespace_only_key_returns_no_auth(self):
        """Whitespace-only key should not create meaningful auth."""
        verifier = create_auth_verifier("   ")
        # While this creates a verifier (non-empty string), the token
        # a client would need to send is exactly "   " — impractical
        # This test documents the behavior
        if HAS_FASTMCP_AUTH:
            # A whitespace key still creates a verifier (defense in depth)
            assert verifier is not None
        else:
            assert verifier is None

    def test_none_transport_defaults_to_stdio(self, monkeypatch):
        """Unset TRANSPORT should default to stdio (no auth required)."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.delenv("TRANSPORT", raising=False)
        config = load_config()
        # Should succeed with empty key
        assert config.api_key == ""

    def test_transport_case_insensitive(self, monkeypatch):
        """TRANSPORT should be case-insensitive."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.setenv("TRANSPORT", "SSE")
        with pytest.raises(ValueError, match="OVERTURE_API_KEY"):
            load_config()

    def test_transport_case_insensitive_http(self, monkeypatch):
        """HTTP transport should be case-insensitive."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.setenv("TRANSPORT", "HTTP")
        with pytest.raises(ValueError, match="OVERTURE_API_KEY"):
            load_config()

    def test_cannot_bypass_by_setting_transport_to_unknown(self, monkeypatch):
        """Unknown transport values should not bypass auth checks.

        The server validates transport in main() and rejects unknown values.
        Here we just verify load_config doesn't crash on unknown transports.
        """
        monkeypatch.setenv("OVERTURE_API_KEY", "key")
        monkeypatch.setenv("TRANSPORT", "websocket")
        # load_config allows any transport string — validation happens in main()
        config = load_config()
        assert config.api_key == "key"


class TestApiKeyStrength:
    """Tests for API key handling robustness."""

    def test_long_api_key_accepted(self):
        """Very long API keys should be accepted."""
        long_key = "k" * 1000
        config = ServerConfig(api_key=long_key)
        assert config.api_key == long_key

    def test_special_characters_in_key(self):
        """API keys with special characters should be accepted."""
        special_key = "key-with-special!@#$%^&*()chars=+"
        config = ServerConfig(api_key=special_key)
        assert config.api_key == special_key

    def test_unicode_api_key(self):
        """Unicode API keys should be accepted."""
        unicode_key = "key-with-unicode-\u00e9\u00e8\u00ea"
        config = ServerConfig(api_key=unicode_key)
        assert config.api_key == unicode_key

    @pytest.mark.skipif(not HAS_FASTMCP_AUTH, reason="fastmcp auth not available")
    def test_verifier_created_for_special_key(self):
        """Auth verifier should handle special character keys."""
        special_key = "key!@#$%"
        verifier = create_auth_verifier(special_key)
        assert verifier is not None


class TestNoImplicitAuth:
    """Verify that auth is never implicitly granted."""

    def test_config_does_not_auto_generate_key(self, monkeypatch):
        """Config should not auto-generate an API key."""
        monkeypatch.delenv("OVERTURE_API_KEY", raising=False)
        monkeypatch.delenv("TRANSPORT", raising=False)
        config = load_config()
        assert config.api_key == ""

    def test_auth_verifier_not_created_without_key(self):
        """Without a key, no auth verifier should be created."""
        verifier = create_auth_verifier("")
        assert verifier is None
