"""
Edge case tests: null and missing parameter handling.

Verifies that null values, missing required params, and unexpected types
are handled gracefully without crashing.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestMissingRequiredParams:
    """Test behavior when required parameters are omitted."""

    async def test_places_missing_lat(self, test_registry):
        """Missing lat should return validation error."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_places_missing_lng(self, test_registry):
        """Missing lng should return validation error."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "radius_m": 500, "category": "cafe",
        })
        assert "error" in result

    async def test_places_missing_radius(self, test_registry):
        """Missing radius should return validation error."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        assert "error" in result

    async def test_places_missing_category(self, test_registry):
        """Missing category should return validation error."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        assert "error" in result

    async def test_buildings_missing_all(self, test_registry):
        """Missing all required params should return error."""
        result = await execute_operation(test_registry, "building_count_in_radius", {})
        assert "error" in result

    async def test_divisions_missing_lat(self, test_registry):
        """Missing lat for divisions should return error."""
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lng": 4.9041,
        })
        assert "error" in result

    async def test_divisions_missing_lng(self, test_registry):
        """Missing lng for divisions should return error."""
        result = await execute_operation(test_registry, "point_in_admin_boundary", {
            "lat": 52.3676,
        })
        assert "error" in result


@pytest.mark.asyncio
class TestNullParams:
    """Test behavior when params are explicitly None."""

    async def test_null_lat(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": None, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert "error" in result

    async def test_null_lng(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": None, "radius_m": 500, "category": "cafe",
        })
        assert "error" in result

    async def test_null_radius(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": None, "category": "cafe",
        })
        assert "error" in result

    async def test_null_category(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": None,
        })
        assert "error" in result


@pytest.mark.asyncio
class TestWrongTypes:
    """Test behavior with wrong parameter types."""

    async def test_string_lat(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": "not_a_number", "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert "error" in result

    async def test_string_radius(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": "big",
        })
        assert "error" in result

    async def test_bool_lat(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": True, "lng": 4.9041, "radius_m": 500,
        })
        # bool is a valid numeric in Python (True=1, False=0)
        # so this should actually succeed (lat=1.0 is valid)
        assert "error" not in result

    async def test_list_lat(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": [52.3676], "lng": 4.9041, "radius_m": 500,
        })
        assert "error" in result

    async def test_dict_lat(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": {"value": 52.3676}, "lng": 4.9041, "radius_m": 500,
        })
        assert "error" in result


@pytest.mark.asyncio
class TestUnknownOperation:
    """Test behavior with non-existent operations."""

    async def test_unknown_operation(self, test_registry):
        result = await execute_operation(test_registry, "does_not_exist", {})
        assert "error" in result
        assert "Unknown operation" in result["error"]

    async def test_typo_in_operation(self, test_registry):
        result = await execute_operation(test_registry, "places_in_raidus", {})
        assert "error" in result

    async def test_empty_operation_name(self, test_registry):
        result = await execute_operation(test_registry, "", {})
        assert "error" in result
