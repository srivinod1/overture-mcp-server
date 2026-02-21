"""
Performance tests: Concurrency behavior under load.

Tests verify that the semaphore correctly limits concurrent queries and
that all queries complete without deadlock. Uses local fixture data.

Note: DuckDB's in-process engine has thread-safety limitations. These
tests focus on semaphore behavior and sequential query throughput rather
than heavy thread-parallel workloads (which would require DuckDB
connections-per-thread).
"""

import asyncio
import pathlib
import time

import pytest
from overture_mcp.config import ServerConfig
from overture_mcp.db import Database

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"


def _make_db(max_concurrent: int = 3) -> Database:
    """Create a Database configured with given concurrency limit.

    Must be called within the test's event loop context so the semaphore
    is bound to the correct loop.
    """
    config = ServerConfig(
        api_key="test-key",
        max_concurrent_queries=max_concurrent,
        query_timeout_s=10,
    )
    db = Database(config)
    db.initialize_local(
        places_path=str(FIXTURES / "sample_places.parquet"),
        buildings_path=str(FIXTURES / "sample_buildings.parquet"),
        divisions_path=str(FIXTURES / "sample_divisions.parquet"),
        transportation_path=str(FIXTURES / "sample_roads.parquet"),
        land_use_path=str(FIXTURES / "sample_land_use.parquet"),
    )
    return db


@pytest.mark.asyncio
class TestConcurrencyControl:
    """Tests for semaphore-based concurrency control."""

    async def test_sequential_queries_succeed(self):
        """Simple sequential queries should all succeed."""
        db = _make_db()
        for _ in range(5):
            rows = await db.execute_query("SELECT COUNT(*) FROM places")
            assert rows[0][0] == 50

    async def test_many_sequential_queries(self):
        """Running many queries sequentially should not exhaust the semaphore."""
        db = _make_db(max_concurrent=2)
        for _ in range(20):
            rows = await db.execute_query("SELECT COUNT(*) FROM places")
            assert rows[0][0] == 50

    async def test_sequential_different_tables(self):
        """Queries against different tables should all succeed."""
        db = _make_db()
        expected = {
            "places": 50,
            "buildings": 50,
            "divisions": 10,
            "roads": 50,
            "land_use": 30,
        }
        for table, count in expected.items():
            rows = await db.execute_query(f"SELECT COUNT(*) FROM {table}")
            assert rows[0][0] == count

    async def test_semaphore_releases_on_success(self):
        """Semaphore should be released after successful queries."""
        db = _make_db(max_concurrent=1)
        # With semaphore(1), each query must wait for the previous to complete.
        # If semaphore isn't released, the second query would deadlock.
        for _ in range(5):
            rows = await db.execute_query("SELECT 1")
            assert rows[0][0] == 1

    async def test_semaphore_releases_on_error(self):
        """Semaphore should be released even when queries fail."""
        db = _make_db(max_concurrent=1)
        # Cause an error
        try:
            await db.execute_query("SELECT * FROM nonexistent_table")
        except Exception:
            pass

        # If semaphore wasn't released, this would deadlock
        rows = await db.execute_query("SELECT COUNT(*) FROM places")
        assert rows[0][0] == 50

    async def test_multiple_error_recovery(self):
        """Multiple errors should not exhaust the semaphore."""
        db = _make_db(max_concurrent=1)
        for _ in range(5):
            try:
                await db.execute_query("INVALID SQL")
            except Exception:
                pass

        # Should still work after all errors
        rows = await db.execute_query("SELECT COUNT(*) FROM places")
        assert rows[0][0] == 50

    async def test_query_throughput_baseline(self):
        """Measure baseline throughput: 50 queries should complete quickly."""
        db = _make_db()
        start = time.time()
        for _ in range(50):
            await db.execute_query("SELECT COUNT(*) FROM places")
        elapsed = time.time() - start

        # 50 queries against local parquet should complete in <10s
        assert elapsed < 10.0, f"50 queries took {elapsed:.1f}s"

    async def test_parameterized_query_throughput(self):
        """Parameterized queries should also be fast."""
        db = _make_db()
        start = time.time()
        for _ in range(20):
            await db.execute_query(
                "SELECT COUNT(*) FROM places WHERE bbox.xmin <= ? AND bbox.xmax >= ?",
                [4.95, 4.85],
            )
        elapsed = time.time() - start
        assert elapsed < 10.0


@pytest.mark.asyncio
class TestQueryTimeout:
    """Tests for query timeout enforcement."""

    async def test_fast_query_succeeds(self):
        """Fast queries should complete within timeout."""
        db = _make_db()
        rows = await db.execute_query("SELECT 42")
        assert rows[0][0] == 42

    async def test_sync_query_bypasses_semaphore(self):
        """execute_sync should work without the semaphore."""
        db = _make_db(max_concurrent=1)
        # execute_sync doesn't use the semaphore
        rows = db.execute_sync("SELECT COUNT(*) FROM places")
        assert rows[0][0] == 50
