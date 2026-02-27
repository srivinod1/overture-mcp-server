"""
E2E test: Customer segmentation workflow.

Simulates an agent profiling a neighborhood's demographic character by
combining building composition, place density, land use, and admin
boundaries — a common pattern for marketing and business intelligence.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestCustomerSegmentation:
    """
    Scenario: A marketing agent profiles Amsterdam center to understand
    the customer base — what businesses exist, what buildings are nearby,
    and what the land use mix looks like.
    """

    async def test_step1_discover_food_categories(self, test_registry):
        """Step 1: Find food-related business categories."""
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "restaurant",
        })
        assert "error" not in result
        assert result["count"] > 0
        cats = {r["category"] for r in result["results"]}
        assert "restaurant" in cats

    async def test_step2_count_restaurants(self, test_registry):
        """Step 2: Count restaurants to gauge dining culture."""
        result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "restaurant",
        })
        assert "error" not in result
        assert result["results"][0]["count"] > 0

    async def test_step3_count_banks(self, test_registry):
        """Step 3: Count banks as economic activity proxy."""
        result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "bank",
        })
        assert "error" not in result
        # May or may not have banks; just verify no error
        assert "count" in result["results"][0]

    async def test_step4_residential_buildings(self, test_registry):
        """Step 4: Check residential building proportion as population indicator."""
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        composition = result["results"][0]["composition"]
        # Fixture data has residential buildings
        assert "residential" in composition

    async def test_step5_residential_land_use(self, test_registry):
        """Step 5: Check residential land use parcels."""
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
            "subtype": "residential",
        })
        assert "error" not in result
        assert result["count"] > 0
        for r in result["results"]:
            assert r["subtype"] == "residential"

    async def test_step6_park_access(self, test_registry):
        """Step 6: Check nearby parks — quality-of-life indicator."""
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
            "subtype": "park",
        })
        assert "error" not in result
        # Should find parks in fixture data
        assert result["count"] > 0

    async def test_step7_walkability_check(self, test_registry):
        """Step 7: Road density as walkability indicator."""
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        assert "error" not in result
        # Dense urban area should have residential roads
        by_class = result["results"][0]["by_class"]
        assert "residential" in by_class

    async def test_multi_category_comparison(self, test_registry):
        """Compare different place categories to profile the neighborhood."""
        categories_to_check = ["cafe", "restaurant", "bank"]
        counts = {}
        for cat in categories_to_check:
            result = await execute_operation(
                test_registry, "count_places_by_type_in_radius",
                {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": cat},
            )
            assert "error" not in result
            counts[cat] = result["results"][0]["count"]

        # All should return valid counts (>= 0)
        for cat, count in counts.items():
            assert count >= 0, f"{cat} returned negative count: {count}"
