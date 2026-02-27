"""
E2E test: Retail site selection workflow.

Simulates an agent evaluating multiple locations for a new retail store by
combining places, buildings, and divisions data across several operations.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestRetailSiteSelection:
    """
    Scenario: An agent evaluates Amsterdam for a new cafe location.
    It queries competitor density, building composition, and admin boundaries.
    """

    async def test_step1_check_categories(self, test_registry):
        """Step 1: Agent discovers valid category IDs for coffee."""
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "coffee",
        })
        assert result["count"] > 0
        cats = [r["category"] for r in result["results"]]
        assert "coffee_shop" in cats

    async def test_step2_count_competitors(self, test_registry):
        """Step 2: Count existing cafes near the proposed location."""
        result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert "error" not in result
        assert result["results"][0]["count"] > 0

    async def test_step3_find_competitors(self, test_registry):
        """Step 3: List nearby cafes with distances."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "cafe", "limit": 100,
        })
        assert result["count"] > 0
        # Results are ordered by distance
        distances = [r["distance_m"] for r in result["results"]]
        assert distances == sorted(distances)

    async def test_step4_check_building_density(self, test_registry):
        """Step 4: Evaluate building density to gauge foot traffic."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        assert result["results"][0]["count"] > 0

    async def test_step5_building_composition(self, test_registry):
        """Step 5: Check if area is commercial/residential."""
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        comp = result["results"][0]["composition"]
        # Composition should have at least one category
        assert len(comp) > 0
        # Percentages should sum to ~100
        total_pct = sum(v["percentage"] for v in comp.values())
        assert abs(total_pct - 100.0) < 0.5

    async def test_step6_admin_boundary(self, test_registry):
        """Step 6: Confirm the location is in Amsterdam, Netherlands."""
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert result["results"][0]["country"] == "Netherlands"
        assert result["results"][0]["locality"] == "Amsterdam"

    async def test_step7_nearest_competitor(self, test_registry):
        """Step 7: Find the single closest competitor."""
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        assert result["count"] == 1
        assert result["results"][0]["distance_m"] >= 0
        assert result["results"][0]["name"] is not None

    async def test_full_workflow_consistency(self, test_registry):
        """Cross-validate: count matches number of places found."""
        count_result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        places_result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "cafe", "limit": 100,
        })
        assert count_result["results"][0]["count"] == places_result["count"]

    async def test_building_count_matches_composition_total(self, test_registry):
        """Cross-validate: building count matches composition total."""
        count_result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
        })
        comp_result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
        })
        assert count_result["results"][0]["count"] == comp_result["results"][0]["total_buildings"]
