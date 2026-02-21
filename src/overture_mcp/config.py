"""
Configuration management for the Overture Maps MCP Server.

All configuration is loaded from environment variables with sensible defaults.
This is the single source of truth for server configuration — no scattered
env var reads elsewhere in the codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_TOOL_MODE = "direct"
DEFAULT_DATA_VERSION = "2026-01-21.0"
DEFAULT_MAX_CONCURRENT_QUERIES = 3
DEFAULT_MAX_RADIUS_M = 50_000
DEFAULT_MAX_RESULTS = 100
DEFAULT_QUERY_TIMEOUT_S = 30
DEFAULT_PORT = 8000
DEFAULT_GEOMETRY_WKT_CAP = 10_000

S3_BUCKET = "overturemaps-us-west-2"
S3_REGION = "us-west-2"

VALID_TOOL_MODES = {"direct", "progressive"}


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServerConfig:
    """Immutable server configuration loaded from environment variables."""

    # Authentication
    api_key: str

    # Tool exposure mode
    tool_mode: str = DEFAULT_TOOL_MODE

    # Overture data
    data_version: str = DEFAULT_DATA_VERSION

    # Query limits
    max_concurrent_queries: int = DEFAULT_MAX_CONCURRENT_QUERIES
    max_radius_m: int = DEFAULT_MAX_RADIUS_M
    max_results: int = DEFAULT_MAX_RESULTS
    query_timeout_s: int = DEFAULT_QUERY_TIMEOUT_S

    # Geometry
    geometry_wkt_cap: int = DEFAULT_GEOMETRY_WKT_CAP

    # Server
    port: int = DEFAULT_PORT

    # Data source overrides (for testing with local fixture data)
    # When set, operations use these instead of S3 paths
    _places_source: str | None = None
    _buildings_source: str | None = None
    _divisions_source: str | None = None
    _transportation_source: str | None = None
    _land_use_source: str | None = None

    def __post_init__(self):
        """Validate config values after initialization."""
        if self.tool_mode not in VALID_TOOL_MODES:
            raise ValueError(
                f"Invalid TOOL_MODE: '{self.tool_mode}'. "
                f"Must be one of: {', '.join(sorted(VALID_TOOL_MODES))}"
            )
        if self.max_concurrent_queries < 1:
            raise ValueError(
                f"MAX_CONCURRENT_QUERIES must be >= 1, got {self.max_concurrent_queries}"
            )
        if self.max_radius_m < 1:
            raise ValueError(
                f"MAX_RADIUS_M must be >= 1, got {self.max_radius_m}"
            )

    # ---------------------------------------------------------------------------
    # S3 path helpers
    # ---------------------------------------------------------------------------

    def s3_path(self, theme: str, type_name: str) -> str:
        """Construct the S3 path for a given Overture theme and type.

        Args:
            theme: Overture theme name (e.g., "places", "buildings", "divisions")
            type_name: Overture type name (e.g., "place", "building", "division_area")

        Returns:
            Full S3 path with glob pattern for reading all parquet files.
        """
        return (
            f"s3://{S3_BUCKET}/release/{self.data_version}"
            f"/theme={theme}/type={type_name}/*"
        )

    @property
    def places_path(self) -> str:
        """Data source for places (S3 path or local override)."""
        if self._places_source:
            return self._places_source
        return self.s3_path("places", "place")

    @property
    def buildings_path(self) -> str:
        """Data source for buildings (S3 path or local override)."""
        if self._buildings_source:
            return self._buildings_source
        return self.s3_path("buildings", "building")

    @property
    def divisions_path(self) -> str:
        """Data source for divisions (S3 path or local override)."""
        if self._divisions_source:
            return self._divisions_source
        return self.s3_path("divisions", "division_area")

    @property
    def transportation_path(self) -> str:
        """Data source for transportation segments (S3 path or local override)."""
        if self._transportation_source:
            return self._transportation_source
        return self.s3_path("transportation", "segment")

    @property
    def land_use_path(self) -> str:
        """Data source for land use (S3 path or local override).

        Note: Land use is under the 'base' theme, not a dedicated theme.
        """
        if self._land_use_source:
            return self._land_use_source
        return self.s3_path("base", "land_use")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config() -> ServerConfig:
    """Load server configuration from environment variables.

    Environment variables:
        OVERTURE_API_KEY: API key for client authentication.
                         Required for HTTP/SSE transports.
                         Optional for stdio transport (local only).
        TOOL_MODE: Optional. "direct" (default) or "progressive".
        OVERTURE_DATA_VERSION: Optional. Overture release version.
        MAX_CONCURRENT_QUERIES: Optional. DuckDB query concurrency limit.
        MAX_RADIUS_M: Optional. Safety cap on radius queries.
        PORT: Optional. Server port.
        TRANSPORT: Optional. "stdio" (default), "sse", or "http".

    Returns:
        ServerConfig instance.

    Raises:
        ValueError: If required env vars are missing or config values are invalid.
    """
    api_key = os.environ.get("OVERTURE_API_KEY", "")
    transport = os.environ.get("TRANSPORT", "stdio").lower()

    if not api_key and transport != "stdio":
        raise ValueError(
            "OVERTURE_API_KEY environment variable is required for "
            f"'{transport}' transport. Set it to a shared secret for "
            "client authentication."
        )

    if not api_key and transport == "stdio":
        import logging
        logging.getLogger(__name__).info(
            "No OVERTURE_API_KEY set. Auth disabled (stdio transport)."
        )

    return ServerConfig(
        api_key=api_key,
        tool_mode=os.environ.get("TOOL_MODE", DEFAULT_TOOL_MODE),
        data_version=os.environ.get("OVERTURE_DATA_VERSION", DEFAULT_DATA_VERSION),
        max_concurrent_queries=int(
            os.environ.get("MAX_CONCURRENT_QUERIES", DEFAULT_MAX_CONCURRENT_QUERIES)
        ),
        max_radius_m=int(
            os.environ.get("MAX_RADIUS_M", DEFAULT_MAX_RADIUS_M)
        ),
        port=int(os.environ.get("PORT", DEFAULT_PORT)),
    )
