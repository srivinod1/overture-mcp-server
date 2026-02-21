"""
DuckDB connection management and concurrency control.

Provides a single point of control for:
- DuckDB connection lifecycle
- Spatial and httpfs extension loading
- S3 region configuration
- Query concurrency limiting via asyncio.Semaphore
- Query timeout enforcement
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import duckdb

from overture_mcp.config import S3_REGION, ServerConfig

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

    def initialize_local(self, places_path: str = "", buildings_path: str = "", divisions_path: str = "") -> None:
        """Initialize DuckDB with local parquet files instead of S3.

        Used for testing with fixture data. Creates views that match
        the table names used in queries.

        Args:
            places_path: Path to local places parquet file.
            buildings_path: Path to local buildings parquet file.
            divisions_path: Path to local divisions parquet file.
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
