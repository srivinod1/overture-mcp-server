"""
E2E test: Advertising and competitor analysis workflow.

Simulates an agent performing competitive intelligence by finding nearby
competitors, measuring distances, and understanding the surrounding
commercial landscape — a common pattern for marketing and media planning.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestAdvertisingCompetitorAnalysis:
    """
    Scenario: A media planning agent evaluates the competitive landscape
    around a proposed billboard location in Amsterdam.
    """

    async def test_step1_find_nearest_competitor(self, test_registry):
        """Step 1: Find the closest cafe to the proposed location."""
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        assert "error" not in result
        assert result["count"] == 1
        nearest = result["results"][0]
        assert nearest["distance_m"] >= 0
        assert "name" in nearest

    async def test_step2_list_all_competitors(self, test_registry):
        """Step 2: List all competing cafes within walking distance."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "cafe", "limit": 50,
        })
        assert "error" not in result
        assert result["count"] > 0
        # Verify distance ordering
        distances = [r["distance_m"] for r in result["results"]]
        assert distances == sorted(distances)

    async def test_step3_nearby_restaurants(self, test_registry):
        """Step 3: Find nearby restaurants as foot traffic indicators."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "restaurant",
        })
        assert "error" not in result
        assert result["count"] > 0

    async def test_step4_commercial_building_presence(self, test_registry):
        """Step 4: Check commercial building presence."""
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        assert "error" not in result
        composition = result["results"][0]["composition"]
        # Area should have commercial buildings
        assert "commercial" in composition

    async def test_step5_commercial_land_use(self, test_registry):
        """Step 5: Verify commercial land use designations."""
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        if result["count"] > 0:
            composition = result["results"][0]["composition"]
            assert len(composition) > 0

    async def test_step6_road_visibility(self, test_registry):
        """Step 6: Check if major roads pass nearby (billboard visibility)."""
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        assert "error" not in result
        total = result["results"][0]["total_segments"]
        assert total > 0

    async def test_nearest_competitor_is_in_radius_results(self, test_registry):
        """Cross-validate: nearest place should appear in radius results."""
        nearest_result = await execute_operation(
            test_registry, "nearest_place_of_type",
            {"lat": 52.3676, "lng": 4.9041, "category": "cafe"},
        )
        radius_result = await execute_operation(
            test_registry, "places_in_radius",
            {"lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
             "category": "cafe", "limit": 100},
        )
        nearest_name = nearest_result["results"][0]["name"]
        radius_names = [r["name"] for r in radius_result["results"]]
        assert nearest_name in radius_names

    async def test_nearest_has_smallest_distance(self, test_registry):
        """Cross-validate: nearest place distance <= all radius place distances."""
        nearest_result = await execute_operation(
            test_registry, "nearest_place_of_type",
            {"lat": 52.3676, "lng": 4.9041, "category": "cafe"},
        )
        radius_result = await execute_operation(
            test_registry, "places_in_radius",
            {"lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
             "category": "cafe", "limit": 100},
        )
        nearest_dist = nearest_result["results"][0]["distance_m"]
        for r in radius_result["results"]:
            assert r["distance_m"] >= nearest_dist - 1  # 1m tolerance
