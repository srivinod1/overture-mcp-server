"""
Security tests: parameter tampering and abuse.

Tests that attempt to bypass validation through creative parameter
manipulation, type coercion tricks, and boundary exploitation.
"""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestRadiusTampering:
    """Attempt to query unreasonably large areas."""

    async def test_max_radius_enforced(self, test_registry):
        """Radius > 50km should be rejected."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 999999,
            "category": "coffee_shop",
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_negative_radius_rejected(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": -1,
            "category": "coffee_shop",
        })
        assert "error" in result


@pytest.mark.asyncio
class TestLimitTampering:
    """Attempt to extract more data than allowed."""

    async def test_huge_limit_rejected(self, test_registry):
        """Limit > 100 should be rejected."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "coffee_shop", "limit": 1000000,
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_negative_limit_rejected(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "coffee_shop", "limit": -1,
        })
        assert "error" in result


@pytest.mark.asyncio
class TestTypeCoercion:
    """Attempt to pass values that might survive type coercion."""

    async def test_string_number_lat(self, test_registry):
        """String '52.3676' should be coerced to float (valid)."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": "52.3676", "lng": "4.9041", "radius_m": "500",
        })
        # String numbers are accepted via float() coercion
        assert "error" not in result

    async def test_string_true_include_geometry(self, test_registry):
        """String 'true' for include_geometry should work."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "coffee_shop", "include_geometry": "true",
        })
        assert "error" not in result

    async def test_integer_coords(self, test_registry):
        """Integer coordinates should be accepted (coerced to float)."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52, "lng": 5, "radius_m": 500,
        })
        assert "error" not in result


@pytest.mark.asyncio
class TestOperationNameTampering:
    """Attempt to access non-existent or internal operations."""

    async def test_internal_name(self, test_registry):
        """Attempt to access internal method names."""
        result = await execute_operation(test_registry, "__init__", {})
        assert "error" in result

    async def test_dunder_name(self, test_registry):
        result = await execute_operation(test_registry, "__class__", {})
        assert "error" in result

    async def test_path_traversal_name(self, test_registry):
        result = await execute_operation(test_registry, "../../../etc/passwd", {})
        assert "error" in result

    async def test_dots_in_name(self, test_registry):
        result = await execute_operation(test_registry, "places.in.radius", {})
        assert "error" in result
