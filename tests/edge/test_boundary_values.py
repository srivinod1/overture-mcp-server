"""
Edge case tests: boundary values for all parameters.

Tests the extremes of valid ranges and boundaries between valid/invalid.
"""

import pytest
from overture_mcp.server import execute_operation
from overture_mcp.validation import ValidationError


@pytest.mark.asyncio
class TestLatitudeBoundaries:
    """Test latitude parameter at valid extremes."""

    async def test_exactly_90(self, test_registry):
        """North pole latitude should be accepted."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 90.0, "lng": 0.0, "radius_m": 1000,
        })
        # No error — valid coordinates, just no data
        assert result["count"] == 0 or "error" not in result

    async def test_exactly_negative_90(self, test_registry):
        """South pole latitude should be accepted."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": -90.0, "lng": 0.0, "radius_m": 1000,
        })
        assert result["count"] == 0 or "error" not in result

    async def test_slightly_over_90(self, test_registry):
        """90.001 should be rejected."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 90.001, "lng": 0.0, "radius_m": 1000,
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_slightly_under_negative_90(self, test_registry):
        """-90.001 should be rejected."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": -90.001, "lng": 0.0, "radius_m": 1000,
        })
        assert "error" in result

    async def test_zero_latitude(self, test_registry):
        """Equator should be accepted."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.0, "lng": 0.0, "radius_m": 1000,
        })
        assert "error" not in result


@pytest.mark.asyncio
class TestLongitudeBoundaries:
    """Test longitude parameter at valid extremes."""

    async def test_exactly_180(self, test_registry):
        """Date line should be accepted."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.0, "lng": 180.0, "radius_m": 1000,
        })
        assert "error" not in result

    async def test_exactly_negative_180(self, test_registry):
        """-180 should be accepted."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.0, "lng": -180.0, "radius_m": 1000,
        })
        assert "error" not in result

    async def test_slightly_over_180(self, test_registry):
        """180.001 should be rejected."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.0, "lng": 180.001, "radius_m": 1000,
        })
        assert "error" in result


@pytest.mark.asyncio
class TestRadiusBoundaries:
    """Test radius parameter at limits."""

    async def test_minimum_radius_1(self, test_registry):
        """Minimum valid radius is 1m."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1,
        })
        assert "error" not in result

    async def test_zero_radius_rejected(self, test_registry):
        """0m radius should be rejected."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 0,
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_negative_radius_rejected(self, test_registry):
        """-100m radius should be rejected."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": -100,
        })
        assert "error" in result

    async def test_max_radius_50000(self, test_registry):
        """50km radius should be accepted (max)."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 50000,
        })
        assert "error" not in result

    async def test_over_max_radius_rejected(self, test_registry):
        """50001m should be rejected."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 50001,
        })
        assert "error" in result


@pytest.mark.asyncio
class TestLimitBoundaries:
    """Test limit parameter at extremes."""

    async def test_limit_1(self, test_registry):
        """Limit of 1 should return at most 1 result."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
            "category": "cafe", "limit": 1,
        })
        assert result["count"] <= 1

    async def test_limit_100(self, test_registry):
        """Limit of 100 (max) should be accepted."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 5000,
            "category": "cafe", "limit": 100,
        })
        assert "error" not in result

    async def test_limit_zero_rejected(self, test_registry):
        """Limit of 0 should be rejected."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "cafe", "limit": 0,
        })
        assert "error" in result

    async def test_limit_over_100_rejected(self, test_registry):
        """Limit of 101 should be rejected."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "cafe", "limit": 101,
        })
        assert "error" in result
