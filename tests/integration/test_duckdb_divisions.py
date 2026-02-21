"""Integration tests for division queries against fixture data."""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestPointInAdminBoundary:
    """Tests for point_in_admin_boundary against fixture data."""

    async def test_returns_hierarchy(self, test_registry, known_divisions_containing_center):
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        admin_levels = result["results"][0]["admin_levels"]
        assert len(admin_levels) == len(known_divisions_containing_center)

    async def test_admin_levels_ascending(self, test_registry):
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        levels = [a["level"] for a in result["results"][0]["admin_levels"]]
        assert levels == sorted(levels)

    async def test_not_in_germany(self, test_registry):
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        names = [a["name"] for a in result["results"][0]["admin_levels"]]
        assert "Germany" not in names
        assert "Bavaria" not in names
        assert "Munich" not in names

    async def test_locality_field(self, test_registry):
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert result["results"][0]["locality"] == "Amsterdam"

    async def test_country_field(self, test_registry):
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert result["results"][0]["country"] == "Netherlands"

    async def test_region_field(self, test_registry):
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert result["results"][0]["region"] == "North Holland"
