"""Integration tests for transportation queries against fixture data."""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestRoadCountByClass:
    """Tests for road_count_by_class against fixture data."""

    async def test_returns_results(self, test_registry):
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        assert result["count"] == 1  # single aggregated result
        assert result["results"][0]["total_segments"] > 0

    async def test_has_by_class_breakdown(self, test_registry):
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        by_class = result["results"][0]["by_class"]
        assert isinstance(by_class, dict)
        # Fixture data has residential roads
        assert "residential" in by_class

    async def test_percentages_sum_to_100(self, test_registry):
        """All class percentages should sum to approximately 100%."""
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        by_class = result["results"][0]["by_class"]
        total_pct = sum(v["percentage"] for v in by_class.values())
        assert abs(total_pct - 100.0) < 0.5  # rounding tolerance

    async def test_counts_sum_to_total(self, test_registry):
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        data = result["results"][0]
        count_sum = sum(v["count"] for v in data["by_class"].values())
        assert count_sum == data["total_segments"]

    async def test_empty_area_returns_suggestion(self, test_registry):
        """Ocean point should have no roads."""
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_response_envelope(self, test_registry):
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "results" in result
        assert "count" in result
        assert "query_params" in result
        assert "data_version" in result


@pytest.mark.asyncio
class TestNearestRoadOfClass:
    """Tests for nearest_road_of_class against fixture data."""

    async def test_returns_one_result(self, test_registry):
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041, "road_class": "residential",
        })
        assert result["count"] == 1

    async def test_result_has_expected_fields(self, test_registry):
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041, "road_class": "residential",
        })
        road = result["results"][0]
        assert "name" in road
        assert "road_class" in road
        assert "road_surface" in road
        assert "distance_m" in road
        assert "lat" in road
        assert "lng" in road
        assert "is_bridge" in road
        assert "is_tunnel" in road
        assert "is_link" in road

    async def test_road_class_matches_request(self, test_registry):
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041, "road_class": "residential",
        })
        assert result["results"][0]["road_class"] == "residential"

    async def test_distance_is_positive(self, test_registry):
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041, "road_class": "residential",
        })
        assert result["results"][0]["distance_m"] >= 0

    async def test_nonexistent_class_in_area(self, test_registry):
        """Looking for a motorway in ocean should return empty."""
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 0.0, "lng": 0.0, "road_class": "motorway",
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_invalid_road_class(self, test_registry):
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041, "road_class": "spaceway",
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"


@pytest.mark.asyncio
class TestRoadSurfaceComposition:
    """Tests for road_surface_composition against fixture data."""

    async def test_returns_results(self, test_registry):
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        assert result["count"] == 1
        assert result["results"][0]["total_segments"] > 0

    async def test_has_composition(self, test_registry):
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        composition = result["results"][0]["composition"]
        assert isinstance(composition, dict)
        # Fixture has roads with various surfaces including 'unknown' for null
        assert len(composition) > 0

    async def test_percentages_sum_to_100(self, test_registry):
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        composition = result["results"][0]["composition"]
        total_pct = sum(v["percentage"] for v in composition.values())
        assert abs(total_pct - 100.0) < 0.5

    async def test_unknown_surface_for_nulls(self, test_registry):
        """Roads with null surface should map to 'unknown'."""
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        composition = result["results"][0]["composition"]
        # Fixture has 8 roads with null surface
        assert "unknown" in composition

    async def test_empty_area(self, test_registry):
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None
