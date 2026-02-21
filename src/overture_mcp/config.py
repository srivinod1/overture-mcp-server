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
        """S3 path for places data."""
        return self.s3_path("places", "place")

    @property
    def buildings_path(self) -> str:
        """S3 path for buildings data."""
        return self.s3_path("buildings", "building")

    @property
    def divisions_path(self) -> str:
        """S3 path for divisions data."""
        return self.s3_path("divisions", "division_area")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config() -> ServerConfig:
    """Load server configuration from environment variables.

    Environment variables:
        OVERTURE_API_KEY: Required. API key for client authentication.
        TOOL_MODE: Optional. "direct" (default) or "progressive".
        OVERTURE_DATA_VERSION: Optional. Overture release version.
        MAX_CONCURRENT_QUERIES: Optional. DuckDB query concurrency limit.
        MAX_RADIUS_M: Optional. Safety cap on radius queries.
        PORT: Optional. Server port.

    Returns:
        ServerConfig instance.

    Raises:
        ValueError: If OVERTURE_API_KEY is not set or config values are invalid.
    """
    api_key = os.environ.get("OVERTURE_API_KEY", "")
    if not api_key:
        raise ValueError(
            "OVERTURE_API_KEY environment variable is required. "
            "Set it to a shared secret for client authentication."
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
