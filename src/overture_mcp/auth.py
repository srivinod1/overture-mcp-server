"""
Authentication for the Overture Maps MCP Server.

Provides API key validation for HTTP-based transports (SSE, Streamable HTTP).
STDIO transport does not use authentication — it inherits security from
its local execution environment.

Clients authenticate via the Authorization header:
    Authorization: Bearer <api-key>

The API key is configured via the OVERTURE_API_KEY environment variable.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# FastMCP auth is optional — only needed for HTTP transports.
try:
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

    HAS_FASTMCP_AUTH = True
except ImportError:
    HAS_FASTMCP_AUTH = False


def create_auth_verifier(api_key: str) -> Any | None:
    """Create an auth verifier for FastMCP HTTP transports.

    Uses FastMCP's StaticTokenVerifier to validate bearer tokens
    against the configured API key.

    Args:
        api_key: The API key to validate against.

    Returns:
        A TokenVerifier instance, or None if fastmcp auth is not available
        or no API key is configured.
    """
    if not api_key:
        logger.warning(
            "No API key configured. HTTP transport will be unauthenticated."
        )
        return None

    if not HAS_FASTMCP_AUTH:
        logger.warning(
            "fastmcp auth not available. HTTP transport will be unauthenticated. "
            "Install fastmcp>=2.0 for auth support."
        )
        return None

    verifier = StaticTokenVerifier(
        tokens={
            api_key: {
                "client_id": "overture-mcp-client",
                "scopes": ["read:data"],
            },
        },
    )
    logger.info("Auth verifier configured for HTTP transport")
    return verifier
