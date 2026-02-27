"""
Edge case tests: empty and no-result scenarios.

Verifies the server handles empty result sets gracefully with
proper suggestion messages and correct envelope structure.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestEmptyPlacesResults:
    """Test empty result handling for places operations."""

    async def test_no_places_at_ocean(self, test_registry):
        """Ocean point should return empty results with suggestion."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500, "category": "cafe",
        })
        assert result["count"] == 0
        assert result["results"] == []
        assert result["suggestion"] is not None
        assert "cafe" in result["suggestion"]

    async def test_empty_envelope_structure(self, test_registry):
        """Empty result should still have full envelope."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500, "category": "cafe",
        })
        assert "results" in result
        assert "count" in result
        assert "query_params" in result
        assert "data_version" in result
        assert "suggestion" in result

    async def test_no_nearest_at_ocean(self, test_registry):
        """Nearest place at ocean point should return empty."""
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 0.0, "lng": 0.0, "category": "cafe",
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_zero_count_at_ocean(self, test_registry):
        """Count at ocean point should be zero with suggestion."""
        result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500, "category": "cafe",
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_category_search_no_match(self, test_registry):
        """Category search with no match should return empty results."""
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "zzz_nonexistent_zzz",
        })
        assert result["count"] == 0
        assert result["results"] == []

    async def test_tiny_radius_misses_all(self, test_registry):
        """1m radius should miss everything (nearest is 95m away)."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1,
            "category": "cafe",
        })
        assert result["count"] == 0


@pytest.mark.asyncio
class TestEmptyBuildingResults:
    """Test empty result handling for building operations."""

    async def test_no_buildings_at_ocean(self, test_registry):
        """Ocean point should have no buildings."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        # Either returns 0 count or empty response
        assert result["count"] == 0 or result.get("results", [{}])[0].get("count", 0) == 0

    async def test_no_composition_at_ocean(self, test_registry):
        """Composition at ocean should return empty with suggestion."""
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None


@pytest.mark.asyncio
class TestEmptyDivisionResults:
    """Test empty result handling for division operations."""

    async def test_no_boundaries_at_ocean(self, test_registry):
        """Ocean point should not be in any admin boundary."""
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 0.0, "lng": 0.0,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None
        assert "international waters" in result["suggestion"] or "limited coverage" in result["suggestion"]


@pytest.mark.asyncio
class TestEmptyTransportationResults:
    """Test empty result handling for transportation operations."""

    async def test_no_roads_at_ocean(self, test_registry):
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_no_nearest_road_at_ocean(self, test_registry):
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 0.0, "lng": 0.0, "road_class": "residential",
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_no_surface_composition_at_ocean(self, test_registry):
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None


@pytest.mark.asyncio
class TestEmptyLandUseResults:
    """Test empty result handling for land use operations."""

    async def test_no_land_use_at_ocean(self, test_registry):
        result = await execute_operation(test_registry, "land_use_at_point", {
            "lat": 0.0, "lng": 0.0,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_no_composition_at_ocean(self, test_registry):
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_no_search_results_at_ocean(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500, "subtype": "residential",
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_tiny_radius_misses_all_land_use(self, test_registry):
        """1m radius should miss all land use parcels."""
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1, "subtype": "residential",
        })
        assert result["count"] == 0
