"""
E2E test: Multi-location comparative analysis.

Simulates an agent comparing multiple geographic points across all three
themes (places, buildings, divisions) — a common pattern for site comparison,
insurance risk assessment, and demographic research.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestMultiLocationAnalysis:
    """Compare Amsterdam center vs a remote ocean point."""

    async def test_populated_area_has_places(self, test_registry):
        """Amsterdam center should have restaurants within 500m."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "restaurant",
        })
        assert result["count"] > 0

    async def test_empty_area_has_no_places(self, test_registry):
        """Gulf of Guinea (0,0) should have no restaurants."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500, "category": "restaurant",
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_populated_area_has_buildings(self, test_registry):
        """Amsterdam center should have buildings."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert result["results"][0]["count"] > 0

    async def test_empty_area_has_no_buildings(self, test_registry):
        """Ocean point should have no buildings."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 1000,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_populated_area_has_boundaries(self, test_registry):
        """Amsterdam is inside known administrative boundaries."""
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert result["count"] == 1
        assert result["results"][0]["country"] is not None

    async def test_ocean_point_no_boundaries(self, test_registry):
        """Gulf of Guinea should not be in any admin boundary."""
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 0.0, "lng": 0.0,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_all_operations_succeed_at_center(self, test_registry):
        """All 7 operations should succeed at Amsterdam center without errors."""
        operations = [
            ("get_place_categories", {"query": "bank"}),
            ("places_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop"}),
            ("nearest_place_of_type", {"lat": 52.3676, "lng": 4.9041, "category": "coffee_shop"}),
            ("count_places_by_type_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop"}),
            ("building_count_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500}),
            ("building_class_composition", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500}),
            ("point_in_admin_boundary", {"lat": 52.3676, "lng": 4.9041}),
        ]

        for op_name, params in operations:
            result = await execute_operation(test_registry, op_name, params)
            assert "error" not in result, f"Operation {op_name} failed: {result}"
