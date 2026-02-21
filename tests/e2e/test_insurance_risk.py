"""
E2E test: Insurance risk assessment workflow.

Simulates an agent evaluating a location's risk profile by combining
building composition, land use classification, road infrastructure, and
admin boundary data — a common pattern for property insurance pricing.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestInsuranceRiskAssessment:
    """
    Scenario: An insurance agent evaluates a property in Amsterdam.
    It checks building density, land use, road access, and admin boundaries
    to build a risk profile.
    """

    async def test_step1_identify_admin_area(self, test_registry):
        """Step 1: Determine what administrative region the property is in."""
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert "error" not in result
        assert result["count"] == 1
        boundary = result["results"][0]
        assert boundary["country"] == "Netherlands"
        assert boundary["locality"] == "Amsterdam"

    async def test_step2_building_density(self, test_registry):
        """Step 2: Assess building density in the area."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        assert "error" not in result
        count = result["results"][0]["count"]
        assert count > 0

    async def test_step3_building_types(self, test_registry):
        """Step 3: Break down building types — residential vs commercial vs industrial."""
        result = await execute_operation(test_registry, "building_class_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        composition = result["results"][0]["composition"]
        assert isinstance(composition, dict)
        # Should have at least one building class
        assert len(composition) > 0
        # Industrial buildings may increase risk
        # Just verify the breakdown is returned
        total_pct = sum(v["percentage"] for v in composition.values())
        assert abs(total_pct - 100.0) < 0.5

    async def test_step4_land_use_classification(self, test_registry):
        """Step 4: Check land use designation at the exact property location."""
        result = await execute_operation(test_registry, "land_use_at_point", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert "error" not in result
        # May or may not be inside a land use polygon
        if result["count"] > 0:
            for r in result["results"]:
                assert "subtype" in r
                assert "class" in r

    async def test_step5_land_use_area_composition(self, test_registry):
        """Step 5: Understand the land use mix in the surrounding area."""
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        if result["count"] > 0:
            composition = result["results"][0]["composition"]
            total_pct = sum(v["percentage"] for v in composition.values())
            assert abs(total_pct - 100.0) < 0.5

    async def test_step6_road_infrastructure(self, test_registry):
        """Step 6: Evaluate road access (fire trucks, emergency vehicles)."""
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        by_class = result["results"][0]["by_class"]
        # Should have roads of at least one class
        assert len(by_class) > 0
        total_segments = result["results"][0]["total_segments"]
        assert total_segments > 0

    async def test_step7_road_surface_quality(self, test_registry):
        """Step 7: Check road surface quality for accessibility assessment."""
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        if result["count"] > 0:
            composition = result["results"][0]["composition"]
            total_pct = sum(v["percentage"] for v in composition.values())
            assert abs(total_pct - 100.0) < 0.5

    async def test_cross_validate_building_data(self, test_registry):
        """Cross-validate: building count matches composition total."""
        count_result = await execute_operation(
            test_registry, "building_count_in_radius",
            {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        )
        comp_result = await execute_operation(
            test_registry, "building_class_composition",
            {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        )
        assert count_result["results"][0]["count"] == comp_result["results"][0]["total_buildings"]

    async def test_cross_validate_road_data(self, test_registry):
        """Cross-validate: road segment count matches composition total."""
        count_result = await execute_operation(
            test_registry, "road_count_by_class",
            {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        )
        surface_result = await execute_operation(
            test_registry, "road_surface_composition",
            {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        )
        assert (
            count_result["results"][0]["total_segments"]
            == surface_result["results"][0]["total_segments"]
        )
