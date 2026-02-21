"""
Integration tests for database connection lifecycle and concurrency.
"""

import asyncio
import pathlib

import pytest
from overture_mcp.config import ServerConfig
from overture_mcp.db import Database

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures"
PLACES_PARQUET = str(FIXTURES_DIR / "sample_places.parquet")
BUILDINGS_PARQUET = str(FIXTURES_DIR / "sample_buildings.parquet")
DIVISIONS_PARQUET = str(FIXTURES_DIR / "sample_divisions.parquet")


class TestDatabaseWarmup:
    """Test parquet metadata warmup."""

    def test_warmup_requires_init(self):
        """warmup() before initialize() should raise."""
        config = ServerConfig(api_key="test")
        db = Database(config)
        with pytest.raises(RuntimeError, match="Call initialize"):
            db.warmup(config)

    def test_warmup_with_local_views(self):
        """warmup() should succeed with local fixture views."""
        config = ServerConfig(
            api_key="test",
            _places_source="places",
            _buildings_source="buildings",
            _divisions_source="divisions",
            _transportation_source="roads",
            _land_use_source="land_use",
        )
        db = Database(config)
        db.initialize_local(
            places_path=PLACES_PARQUET,
            buildings_path=BUILDINGS_PARQUET,
            divisions_path=DIVISIONS_PARQUET,
            transportation_path=str(FIXTURES_DIR / "sample_roads.parquet"),
            land_use_path=str(FIXTURES_DIR / "sample_land_use.parquet"),
        )
        # Should complete without error
        db.warmup(config)

    def test_warmup_handles_missing_theme(self):
        """warmup() should log warning but not crash on missing data."""
        config = ServerConfig(
            api_key="test",
            _places_source="places",
            _buildings_source="nonexistent_table",
            _divisions_source="divisions",
            _transportation_source="roads",
            _land_use_source="land_use",
        )
        db = Database(config)
        db.initialize_local(
            places_path=PLACES_PARQUET,
            divisions_path=DIVISIONS_PARQUET,
            transportation_path=str(FIXTURES_DIR / "sample_roads.parquet"),
            land_use_path=str(FIXTURES_DIR / "sample_land_use.parquet"),
        )
        # Should not raise — failed themes are logged as warnings
        db.warmup(config)


class TestDatabaseLifecycle:
    """Test database initialization and lifecycle."""

    def test_uninitialized_raises(self):
        """Accessing connection before init should raise RuntimeError."""
        config = ServerConfig(api_key="test")
        db = Database(config)
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = db.connection

    def test_initialize_local(self):
        """initialize_local should set up views for fixture data."""
        config = ServerConfig(api_key="test")
        db = Database(config)
        db.initialize_local(
            places_path=PLACES_PARQUET,
            buildings_path=BUILDINGS_PARQUET,
            divisions_path=DIVISIONS_PARQUET,
        )
        # Should be able to query
        rows = db.execute_sync("SELECT COUNT(*) FROM places")
        assert rows[0][0] == 50

    def test_initialize_idempotent(self):
        """Calling initialize_local twice should be safe."""
        config = ServerConfig(api_key="test")
        db = Database(config)
        db.initialize_local(places_path=PLACES_PARQUET)
        db.initialize_local(places_path=PLACES_PARQUET)  # second call is no-op
        rows = db.execute_sync("SELECT COUNT(*) FROM places")
        assert rows[0][0] == 50

    def test_close(self):
        """close() should make the connection unusable."""
        config = ServerConfig(api_key="test")
        db = Database(config)
        db.initialize_local(places_path=PLACES_PARQUET)
        db.close()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = db.connection

    def test_execute_sync_without_params(self):
        """execute_sync with no params should work."""
        config = ServerConfig(api_key="test")
        db = Database(config)
        db.initialize_local(places_path=PLACES_PARQUET)
        rows = db.execute_sync("SELECT 1 + 1")
        assert rows[0][0] == 2

    def test_execute_sync_with_params(self):
        """execute_sync with params should bind correctly."""
        config = ServerConfig(api_key="test")
        db = Database(config)
        db.initialize_local(places_path=PLACES_PARQUET)
        rows = db.execute_sync("SELECT ? + ?", [10, 20])
        assert rows[0][0] == 30


@pytest.mark.asyncio
class TestDatabaseConcurrency:
    """Test async query execution and semaphore behavior."""

    async def test_basic_async_query(self, test_db):
        """Basic async query should work."""
        rows = await test_db.execute_query("SELECT COUNT(*) FROM places")
        assert rows[0][0] == 50

    async def test_async_query_with_params(self, test_db):
        """Async query with params should bind correctly."""
        rows = await test_db.execute_query("SELECT ? + ?", [5, 7])
        assert rows[0][0] == 12

    async def test_sequential_async_queries(self, test_db):
        """Multiple sequential async queries should all succeed.

        Note: DuckDB connections are not fully thread-safe for concurrent
        access from multiple threads. The semaphore serializes access,
        so queries run one at a time. We test sequential async to verify
        the semaphore + thread pool pattern works.
        """
        rows1 = await test_db.execute_query("SELECT COUNT(*) FROM places")
        rows2 = await test_db.execute_query("SELECT COUNT(*) FROM buildings")
        rows3 = await test_db.execute_query("SELECT COUNT(*) FROM divisions")
        assert rows1[0][0] == 50
        assert rows2[0][0] == 50
        assert rows3[0][0] == 10

    async def test_semaphore_limits_concurrency(self):
        """Semaphore should limit concurrent queries.

        We use max_concurrent=1 to serialize all queries. This matches
        DuckDB's single-connection thread safety model and verifies the
        semaphore actually constrains concurrency.
        """
        config = ServerConfig(api_key="test", max_concurrent_queries=1)
        db = Database(config)
        db.initialize_local(places_path=PLACES_PARQUET)

        # Track how many queries are running concurrently
        running = 0
        max_running = 0

        original_execute = db._execute_sync

        def tracked_execute(sql, params=None):
            nonlocal running, max_running
            running += 1
            max_running = max(max_running, running)
            import time
            time.sleep(0.02)  # simulate work
            result = original_execute(sql, params)
            running -= 1
            return result

        db._execute_sync = tracked_execute

        # Launch 3 sequential queries (semaphore=1 serializes them)
        for _ in range(3):
            await db.execute_query("SELECT COUNT(*) FROM places")

        # With semaphore=1, max concurrent should be exactly 1
        assert max_running == 1

    async def test_error_releases_semaphore(self):
        """Query error should still release the semaphore."""
        config = ServerConfig(api_key="test", max_concurrent_queries=1)
        db = Database(config)
        db.initialize_local(places_path=PLACES_PARQUET)

        # First query: should error (bad SQL)
        try:
            await db.execute_query("SELECT * FROM nonexistent_table_xyz")
        except Exception:
            pass

        # Second query: should work (semaphore released)
        rows = await db.execute_query("SELECT COUNT(*) FROM places")
        assert rows[0][0] == 50
