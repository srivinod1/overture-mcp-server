"""
Performance tests: Latency baselines for operations against fixture data.

These tests establish baseline latency expectations for each operation
against local fixture data. They help catch performance regressions.

Note: Latency against S3 will be significantly higher (2-10x) than local
fixture data. These baselines only catch code-level regressions.
"""

import time

import pytest
from overture_mcp.server import execute_operation


# Maximum acceptable latency for operations against local fixture data.
# These are generous limits — actual times should be well under 100ms.
MAX_OPERATION_LATENCY_S = 2.0


@pytest.mark.asyncio
class TestPlacesLatency:
    """Latency baselines for places operations."""

    async def test_get_place_categories_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "coffee",
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_places_in_radius_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_nearest_place_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_count_places_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S


@pytest.mark.asyncio
class TestBuildingsLatency:
    """Latency baselines for buildings operations."""

    async def test_building_count_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_building_composition_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S


@pytest.mark.asyncio
class TestDivisionsLatency:
    """Latency baselines for divisions operations."""

    async def test_admin_boundary_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S


@pytest.mark.asyncio
class TestTransportationLatency:
    """Latency baselines for transportation operations."""

    async def test_road_count_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_nearest_road_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041, "road_class": "residential",
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_road_surface_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S


@pytest.mark.asyncio
class TestLandUseLatency:
    """Latency baselines for land use operations."""

    async def test_land_use_at_point_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "land_use_at_point", {
            "lat": 52.3676, "lng": 4.9041,
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_land_use_composition_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_land_use_search_latency(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000, "subtype": "residential",
        })
        elapsed = time.time() - start
        assert "error" not in result
        assert elapsed < MAX_OPERATION_LATENCY_S


@pytest.mark.asyncio
class TestEmptyAreaLatency:
    """Latency for empty-area queries (should be fast — no data to process)."""

    async def test_empty_places_fast(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500, "category": "cafe",
        })
        elapsed = time.time() - start
        assert result["count"] == 0
        assert elapsed < MAX_OPERATION_LATENCY_S

    async def test_empty_buildings_fast(self, test_registry):
        start = time.time()
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        elapsed = time.time() - start
        assert result["count"] == 0
        assert elapsed < MAX_OPERATION_LATENCY_S
