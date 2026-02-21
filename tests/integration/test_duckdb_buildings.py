"""Integration tests for building queries against fixture data."""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestBuildingCount:
    """Tests for building_count_in_radius against fixture data."""

    async def test_total_count(self, test_registry):
        """Large radius should capture all 50 fixture buildings."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
        })
        assert result["results"][0]["count"] == 50

    async def test_smaller_radius_fewer_buildings(self, test_registry):
        """200m radius should capture fewer than 50 buildings."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 200,
        })
        assert result["results"][0]["count"] < 50
        assert result["results"][0]["count"] > 0


@pytest.mark.asyncio
class TestBuildingComposition:
    """Tests for building_class_composition against fixture data."""

    async def test_composition_percentages(self, test_registry, known_building_composition):
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
        })
        comp = result["results"][0]["composition"]
        assert comp["residential"]["count"] == known_building_composition["residential"]
        assert comp["commercial"]["count"] == known_building_composition["commercial"]
        assert comp["industrial"]["count"] == known_building_composition["industrial"]
        assert comp["unknown"]["count"] == known_building_composition["unknown"]

    async def test_percentages_sum_to_100(self, test_registry):
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
        })
        comp = result["results"][0]["composition"]
        total_pct = sum(v["percentage"] for v in comp.values())
        assert abs(total_pct - 100.0) < 0.5  # allow rounding

    async def test_count_matches_total(self, test_registry):
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
        })
        r = result["results"][0]
        total_from_composition = sum(v["count"] for v in r["composition"].values())
        assert total_from_composition == r["total_buildings"]

    async def test_null_class_mapped_to_unknown(self, test_registry):
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
        })
        comp = result["results"][0]["composition"]
        assert "unknown" in comp
        assert comp["unknown"]["count"] > 0
