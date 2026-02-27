"""
E2E test: Multi-MCP integration workflow.

Simulates an agent using Overture MCP alongside a hypothetical geocoding MCP.
Since we don't have a real geocoding MCP in tests, we simulate the geocoding
step by providing known coordinates, then verify the Overture operations
work correctly in sequence — matching how a real agent would chain MCPs.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestMultiMcpWorkflow:
    """
    Scenario: An agent compares two neighborhoods using geocoded addresses.
    The geocoding step is simulated with known coordinates.
    """

    # Simulated geocode results (as if returned by a Geocoding MCP)
    LOCATION_A = {"name": "Amsterdam Center", "lat": 52.3676, "lng": 4.9041}
    LOCATION_B = {"name": "Gulf of Guinea", "lat": 0.0, "lng": 0.0}

    async def test_step1_identify_both_regions(self, test_registry):
        """Step 1: Agent identifies admin regions for both locations."""
        result_a = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": self.LOCATION_A["lat"], "lng": self.LOCATION_A["lng"],
        })
        result_b = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": self.LOCATION_B["lat"], "lng": self.LOCATION_B["lng"],
        })
        # Location A is in Amsterdam
        assert result_a["count"] == 1
        assert result_a["results"][0]["country"] == "Netherlands"
        # Location B is in the ocean — no admin boundary
        assert result_b["count"] == 0

    async def test_step2_compare_building_density(self, test_registry):
        """Step 2: Compare building density between locations."""
        result_a = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": self.LOCATION_A["lat"], "lng": self.LOCATION_A["lng"],
            "radius_m": 1000,
        })
        result_b = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": self.LOCATION_B["lat"], "lng": self.LOCATION_B["lng"],
            "radius_m": 1000,
        })
        count_a = result_a["results"][0]["count"]
        # Ocean has no buildings
        assert result_b["count"] == 0
        # Amsterdam has many
        assert count_a > 0

    async def test_step3_compare_road_networks(self, test_registry):
        """Step 3: Compare road infrastructure."""
        result_a = await execute_operation(test_registry, "road_count_by_class", {
            "lat": self.LOCATION_A["lat"], "lng": self.LOCATION_A["lng"],
            "radius_m": 1000,
        })
        result_b = await execute_operation(test_registry, "road_count_by_class", {
            "lat": self.LOCATION_B["lat"], "lng": self.LOCATION_B["lng"],
            "radius_m": 1000,
        })
        # Amsterdam has roads
        assert result_a["results"][0]["total_segments"] > 0
        # Ocean has none
        assert result_b["count"] == 0

    async def test_step4_compare_land_use(self, test_registry):
        """Step 4: Compare land use patterns."""
        result_a = await execute_operation(test_registry, "land_use_composition", {
            "lat": self.LOCATION_A["lat"], "lng": self.LOCATION_A["lng"],
            "radius_m": 1000,
        })
        result_b = await execute_operation(test_registry, "land_use_composition", {
            "lat": self.LOCATION_B["lat"], "lng": self.LOCATION_B["lng"],
            "radius_m": 500,
        })
        # Amsterdam has land use data
        if result_a["count"] > 0:
            comp = result_a["results"][0]["composition"]
            assert len(comp) > 0
        # Ocean has none
        assert result_b["count"] == 0

    async def test_step5_compare_commercial_places(self, test_registry):
        """Step 5: Compare commercial activity via place counts."""
        categories_to_check = ["restaurant", "cafe"]
        for cat in categories_to_check:
            result_a = await execute_operation(
                test_registry, "count_places_by_type_in_radius",
                {"lat": self.LOCATION_A["lat"], "lng": self.LOCATION_A["lng"],
                 "radius_m": 500, "category": cat},
            )
            result_b = await execute_operation(
                test_registry, "count_places_by_type_in_radius",
                {"lat": self.LOCATION_B["lat"], "lng": self.LOCATION_B["lng"],
                 "radius_m": 500, "category": cat},
            )
            # Amsterdam has places
            assert result_a["results"][0]["count"] > 0
            # Ocean has none — empty results list, count=0 in envelope
            assert result_b["count"] == 0

    async def test_empty_area_suggestions(self, test_registry):
        """Verify all operations return suggestions for empty areas."""
        empty_operations = [
            ("places_in_radius", {"lat": 0.0, "lng": 0.0, "radius_m": 500, "category": "restaurant"}),
            ("building_count_in_radius", {"lat": 0.0, "lng": 0.0, "radius_m": 500}),
            ("point_in_admin_boundary", {"lat": 0.0, "lng": 0.0}),
            ("road_count_by_class", {"lat": 0.0, "lng": 0.0, "radius_m": 500}),
            ("land_use_composition", {"lat": 0.0, "lng": 0.0, "radius_m": 500}),
        ]
        for op_name, params in empty_operations:
            result = await execute_operation(test_registry, op_name, params)
            assert result["count"] == 0, f"{op_name} returned non-zero at ocean point"
            assert result.get("suggestion") is not None, f"{op_name} missing suggestion"

    async def test_all_themes_accessible_from_single_point(self, test_registry):
        """All 5 themes should return data for Amsterdam center."""
        theme_operations = {
            "places": ("places_in_radius", {
                "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
            }),
            "buildings": ("building_count_in_radius", {
                "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            }),
            "divisions": ("point_in_admin_boundary", {
                "lat": 52.3676, "lng": 4.9041,
            }),
            "transportation": ("road_count_by_class", {
                "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            }),
            "land_use": ("land_use_at_point", {
                "lat": 52.3676, "lng": 4.9041,
            }),
        }
        for theme, (op_name, params) in theme_operations.items():
            result = await execute_operation(test_registry, op_name, params)
            assert "error" not in result, f"Theme '{theme}' ({op_name}) failed: {result}"
