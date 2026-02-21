"""
Performance tests: Memory usage monitoring.

Tests verify that operations don't leak memory across repeated calls.
Uses local fixture data — memory characteristics against S3 will differ.
"""

import pytest

# psutil is an optional dev dependency
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from overture_mcp.server import execute_operation


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_PSUTIL, reason="psutil not installed")
class TestMemoryUsage:
    """Tests for memory behavior under repeated operations."""

    async def test_no_memory_leak_across_repeated_queries(self, test_registry):
        """Running the same operation many times should not leak memory."""
        import os
        process = psutil.Process(os.getpid())

        # Warm up
        for _ in range(5):
            await execute_operation(test_registry, "places_in_radius", {
                "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
                "category": "coffee_shop",
            })

        mem_before = process.memory_info().rss

        # Run 50 queries
        for _ in range(50):
            await execute_operation(test_registry, "places_in_radius", {
                "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
                "category": "coffee_shop",
            })

        mem_after = process.memory_info().rss
        mem_growth_mb = (mem_after - mem_before) / (1024 * 1024)

        # Memory growth should be minimal (< 50MB for 50 queries)
        assert mem_growth_mb < 50, f"Memory grew by {mem_growth_mb:.1f} MB"

    async def test_no_leak_across_different_operations(self, test_registry):
        """Mixed operations should not leak memory."""
        import os
        process = psutil.Process(os.getpid())

        operations = [
            ("get_place_categories", {"query": "coffee"}),
            ("places_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop"}),
            ("building_count_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500}),
            ("point_in_admin_boundary", {"lat": 52.3676, "lng": 4.9041}),
            ("road_count_by_class", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500}),
            ("land_use_at_point", {"lat": 52.3676, "lng": 4.9041}),
        ]

        # Warm up
        for op_name, params in operations:
            await execute_operation(test_registry, op_name, params)

        mem_before = process.memory_info().rss

        # Run 10 cycles through all operations
        for _ in range(10):
            for op_name, params in operations:
                await execute_operation(test_registry, op_name, params)

        mem_after = process.memory_info().rss
        mem_growth_mb = (mem_after - mem_before) / (1024 * 1024)

        assert mem_growth_mb < 50, f"Memory grew by {mem_growth_mb:.1f} MB"

    async def test_error_queries_dont_leak(self, test_registry):
        """Error responses should not leak memory."""
        import os
        process = psutil.Process(os.getpid())

        mem_before = process.memory_info().rss

        # Run 50 invalid queries
        for _ in range(50):
            await execute_operation(test_registry, "places_in_radius", {
                "lat": 999, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
            })

        mem_after = process.memory_info().rss
        mem_growth_mb = (mem_after - mem_before) / (1024 * 1024)

        assert mem_growth_mb < 20, f"Memory grew by {mem_growth_mb:.1f} MB on errors"
