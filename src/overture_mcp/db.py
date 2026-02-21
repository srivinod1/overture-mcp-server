"""
DuckDB connection management and concurrency control.

Provides a single point of control for:
- DuckDB connection lifecycle
- Spatial and httpfs extension loading
- S3 region configuration
- STAC index loading for targeted S3 file resolution
- Query concurrency limiting via asyncio.Semaphore
- Query timeout enforcement
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import duckdb

from overture_mcp.config import S3_REGION, ServerConfig
from overture_mcp.stac import StacIndex

logger = logging.getLogger(__name__)


class Database:
    """DuckDB database connection manager with concurrency control.

    The connection is read-only against S3 — no state is mutated.
    A semaphore limits concurrent queries to prevent OOM on constrained
    environments (Railway Hobby plan: 512MB-1GB RAM).

    When all semaphore slots are in use, new queries queue. No query is
    dropped. The timeout applies per-query (not including queue wait time).
    If a query errors or times out, the semaphore is always released.
    """

    def __init__(self, config: ServerConfig):
        self._config = config
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._semaphore = asyncio.Semaphore(config.max_concurrent_queries)
        self._initialized = False
        self._stac = StacIndex()

    @property
    def stac(self) -> StacIndex:
        """The STAC index for targeted S3 file resolution."""
        return self._stac

    def initialize(self) -> None:
        """Initialize the DuckDB connection with required extensions.

        Call once at server startup. Loads spatial and httpfs extensions,
        configures S3 region for anonymous access to Overture bucket.
        """
        if self._initialized:
            return

        logger.info("Initializing DuckDB connection...")
        self._conn = duckdb.connect(":memory:")

        # Load required extensions
        self._conn.execute("INSTALL spatial; LOAD spatial;")
        self._conn.execute("INSTALL httpfs; LOAD httpfs;")

        # Configure S3 for anonymous access to Overture bucket
        self._conn.execute(f"SET s3_region='{S3_REGION}';")

        self._initialized = True
        logger.info("DuckDB initialized with spatial + httpfs extensions")

    def load_stac_index(self) -> None:
        """Download and cache the STAC index for targeted file resolution.

        Uses the DuckDB connection to fetch the STAC GeoParquet index from
        Overture's STAC endpoint. This is a small (~100-500KB) download that
        enables resolving which S3 files contain data for a given bbox.

        Must be called after initialize(). If loading fails, the server
        falls back to glob patterns (slower cold starts but still functional).
        """
        if not self._initialized or self._conn is None:
            raise RuntimeError("Call initialize() before load_stac_index().")

        self._stac.load(self._conn, self._config.data_version)

    def resolve_source(
        self,
        collection: str,
        lat: float,
        lng: float,
        radius_m: int,
        fallback: str,
    ) -> str:
        """Resolve the data source for a query using STAC index.

        If the STAC index is loaded, finds only the S3 files that overlap
        the query's bounding box and returns a read_parquet([...]) fragment.
        Otherwise falls back to the glob pattern from config.

        Args:
            collection: STAC collection name (e.g., "place", "building").
            lat: Query center latitude.
            lng: Query center longitude.
            radius_m: Query radius in meters.
            fallback: Glob-based read_parquet() string from config (used if
                      STAC is unavailable or no files match).

        Returns:
            SQL data source string (either targeted file list or glob).
        """
        resolved = self._stac.resolve(collection, lat, lng, radius_m)
        return resolved if resolved is not None else fallback

    def resolve_source_point(
        self,
        collection: str,
        lat: float,
        lng: float,
        fallback: str,
    ) -> str:
        """Resolve data source for a point-in-polygon query.

        Like resolve_source but for operations without a radius
        (e.g., point_in_admin_boundary, land_use_at_point).

        Args:
            collection: STAC collection name.
            lat: Query point latitude.
            lng: Query point longitude.
            fallback: Glob-based fallback from config.

        Returns:
            SQL data source string.
        """
        resolved = self._stac.resolve_for_point(collection, lat, lng)
        return resolved if resolved is not None else fallback

    def warmup(self, config: ServerConfig) -> None:
        """Pre-fetch parquet metadata from S3 for all themes.

        DuckDB caches parquet file footers (row group statistics) after the
        first query against each file. Without warmup, the first agent query
        per theme pays a ~10-30s cold-start penalty while metadata is fetched.
        This method runs a minimal query (LIMIT 0) against each theme to force
        the metadata download so all subsequent queries are fast (<5s).

        Should be called once at server startup, after initialize().
        """
        if not self._initialized:
            raise RuntimeError("Call initialize() before warmup().")

        theme_paths = [
            ("places", config.places_path),
            ("buildings", config.buildings_path),
            ("divisions", config.divisions_path),
            ("transportation", config.transportation_path),
            ("land_use", config.land_use_path),
        ]

        logger.info("Warming up parquet metadata cache for %d themes...", len(theme_paths))
        total_start = time.time()

        for name, path in theme_paths:
            start = time.time()
            try:
                self._conn.execute(f"SELECT 1 FROM {path} LIMIT 0")
                elapsed = time.time() - start
                logger.info("  %s metadata cached in %.1fs", name, elapsed)
            except Exception as e:
                elapsed = time.time() - start
                logger.warning("  %s warmup failed after %.1fs: %s", name, elapsed, e)

        total_elapsed = time.time() - total_start
        logger.info("Metadata warmup complete in %.1fs", total_elapsed)

    def initialize_local(
        self,
        places_path: str = "",
        buildings_path: str = "",
        divisions_path: str = "",
        transportation_path: str = "",
        land_use_path: str = "",
    ) -> None:
        """Initialize DuckDB with local parquet files instead of S3.

        Used for testing with fixture data. Creates views that match
        the table names used in queries.

        Args:
            places_path: Path to local places parquet file.
            buildings_path: Path to local buildings parquet file.
            divisions_path: Path to local divisions parquet file.
            transportation_path: Path to local roads parquet file.
            land_use_path: Path to local land use parquet file.
        """
        if self._initialized:
            return

        logger.info("Initializing DuckDB with local fixture data...")
        self._conn = duckdb.connect(":memory:")
        self._conn.execute("INSTALL spatial; LOAD spatial;")

        if places_path:
            self._conn.execute(
                f"CREATE VIEW places AS SELECT * FROM read_parquet('{places_path}')"
            )
        if buildings_path:
            self._conn.execute(
                f"CREATE VIEW buildings AS SELECT * FROM read_parquet('{buildings_path}')"
            )
        if divisions_path:
            self._conn.execute(
                f"CREATE VIEW divisions AS SELECT * FROM read_parquet('{divisions_path}')"
            )
        if transportation_path:
            self._conn.execute(
                f"CREATE VIEW roads AS SELECT * FROM read_parquet('{transportation_path}')"
            )
        if land_use_path:
            self._conn.execute(
                f"CREATE VIEW land_use AS SELECT * FROM read_parquet('{land_use_path}')"
            )

        self._initialized = True
        logger.info("DuckDB initialized with local fixture data")

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Get the raw DuckDB connection. Raises if not initialized."""
        if not self._initialized or self._conn is None:
            raise RuntimeError(
                "Database not initialized. Call initialize() or initialize_local() first."
            )
        return self._conn

    async def execute_query(
        self, sql: str, params: list[Any] | None = None
    ) -> list[tuple]:
        """Execute a SQL query with concurrency control and timeout.

        Acquires a semaphore slot, runs the query in a thread pool (to avoid
        blocking the event loop), and returns results. The semaphore is always
        released, even if the query errors or times out.

        Args:
            sql: SQL query string with ? placeholders for parameters.
            params: List of parameter values to bind to ? placeholders.

        Returns:
            List of result tuples.

        Raises:
            asyncio.TimeoutError: If query exceeds timeout.
            RuntimeError: If database is not initialized.
            duckdb.Error: If the query fails.
        """
        async with self._semaphore:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._execute_sync, sql, params),
                timeout=self._config.query_timeout_s,
            )

    def _execute_sync(
        self, sql: str, params: list[Any] | None = None
    ) -> list[tuple]:
        """Synchronous query execution (runs in thread pool)."""
        conn = self.connection
        if params:
            result = conn.execute(sql, params)
        else:
            result = conn.execute(sql)
        return result.fetchall()

    def execute_sync(
        self, sql: str, params: list[Any] | None = None
    ) -> list[tuple]:
        """Execute a query synchronously without semaphore.

        Used for simple operations like health checks and category loading
        that don't need concurrency control.
        """
        return self._execute_sync(sql, params)

    def close(self) -> None:
        """Close the DuckDB connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._initialized = False
            logger.info("DuckDB connection closed")
