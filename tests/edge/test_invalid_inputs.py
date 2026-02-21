"""
Edge case tests: invalid input combinations and unusual values.

Tests NaN, Infinity, extremely large numbers, unicode, and
other unusual but possible input patterns.
"""

import math

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestSpecialFloatValues:
    """Test handling of NaN, Infinity, and other special float values."""

    async def test_nan_lat(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": float("nan"), "lng": 4.9041, "radius_m": 500,
        })
        assert "error" in result

    async def test_nan_lng(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": float("nan"), "radius_m": 500,
        })
        assert "error" in result

    async def test_inf_lat(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": float("inf"), "lng": 4.9041, "radius_m": 500,
        })
        assert "error" in result

    async def test_neg_inf_lng(self, test_registry):
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": float("-inf"), "radius_m": 500,
        })
        assert "error" in result

    async def test_very_small_float_lat(self, test_registry):
        """Very small float near zero should be valid."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 0.000001, "lng": 0.000001, "radius_m": 500,
        })
        assert "error" not in result


@pytest.mark.asyncio
class TestExtremeRadius:
    """Test radius values at extreme ends."""

    async def test_radius_exactly_50000(self, test_registry):
        """Max radius should work."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 50000,
        })
        assert "error" not in result

    async def test_radius_very_large(self, test_registry):
        """100000m should be rejected."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 100000,
        })
        assert "error" in result

    async def test_radius_float_truncated(self, test_registry):
        """Float radius should be truncated to int."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500.7,
        })
        assert "error" not in result


@pytest.mark.asyncio
class TestUnicodeInputs:
    """Test handling of unicode in string parameters."""

    async def test_unicode_category(self, test_registry):
        """Unicode category should be rejected (not in taxonomy)."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "\u2615\u2615\u2615",  # coffee emoji
        })
        assert "error" in result

    async def test_unicode_query(self, test_registry):
        """Unicode in category search should work (return no results)."""
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "\u30e9\u30fc\u30e1\u30f3",  # "ramen" in Japanese
        })
        # Should not crash, just return 0 results
        assert "error" not in result
        assert result["count"] >= 0


@pytest.mark.asyncio
class TestEmptyParams:
    """Test with empty param dict."""

    async def test_empty_params_for_categories(self, test_registry):
        """get_place_categories with no params should return all categories."""
        result = await execute_operation(test_registry, "get_place_categories", {})
        assert result["count"] > 0

    async def test_empty_params_for_places(self, test_registry):
        """places_in_radius with no params should fail validation."""
        result = await execute_operation(test_registry, "places_in_radius", {})
        assert "error" in result


@pytest.mark.asyncio
class TestExtraParams:
    """Test with extra unexpected parameters — should be silently ignored."""

    async def test_extra_params_ignored(self, test_registry):
        """Extra params should not cause errors."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "extra_param": "should_be_ignored",
            "another_extra": 42,
        })
        assert "error" not in result


@pytest.mark.asyncio
class TestTransportationInvalidInputs:
    """Invalid inputs for transportation operations."""

    async def test_missing_road_class(self, test_registry):
        """nearest_road_of_class requires road_class."""
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert "error" in result

    async def test_invalid_road_class(self, test_registry):
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041, "road_class": "spaceway",
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_road_count_missing_radius(self, test_registry):
        result = await execute_operation(test_registry, "road_count_by_class", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert "error" in result

    async def test_road_surface_nan_lat(self, test_registry):
        result = await execute_operation(test_registry, "road_surface_composition", {
            "lat": float("nan"), "lng": 4.9041, "radius_m": 500,
        })
        assert "error" in result


@pytest.mark.asyncio
class TestLandUseInvalidInputs:
    """Invalid inputs for land use operations."""

    async def test_missing_subtype_for_search(self, test_registry):
        """land_use_search requires subtype."""
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
        })
        assert "error" in result

    async def test_invalid_subtype(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "subtype": "moonbase",
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_land_use_at_point_missing_params(self, test_registry):
        result = await execute_operation(test_registry, "land_use_at_point", {})
        assert "error" in result

    async def test_land_use_composition_inf_lng(self, test_registry):
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": float("inf"), "radius_m": 500,
        })
        assert "error" in result
