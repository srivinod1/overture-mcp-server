"""Integration tests for places queries against fixture data."""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestPlacesInRadius:
    """Tests for places_in_radius against fixture data."""

    async def test_returns_correct_count(self, test_registry, known_coffee_shops_within_500m):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
        })
        assert result["count"] == known_coffee_shops_within_500m

    async def test_ordered_by_distance(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
        })
        distances = [r["distance_m"] for r in result["results"]]
        assert distances == sorted(distances)

    async def test_distance_accuracy(self, test_registry, known_nearest_coffee_shop):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
        })
        nearest = result["results"][0]
        assert nearest["name"] == known_nearest_coffee_shop["name"]
        # Allow 2m tolerance for spheroid vs fixture approximation
        assert abs(nearest["distance_m"] - known_nearest_coffee_shop["distance_m"]) <= 2

    async def test_respects_limit(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
            "limit": 3,
        })
        assert result["count"] == 3

    async def test_excludes_outside_radius(self, test_registry):
        """400m radius should exclude coffee shops at 420m+."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 400, "category": "coffee_shop",
        })
        for r in result["results"]:
            assert r["distance_m"] < 400

    async def test_result_has_required_fields(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
        })
        for r in result["results"]:
            assert "name" in r
            assert "category" in r
            assert "lat" in r
            assert "lng" in r
            assert "distance_m" in r

    async def test_response_envelope(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
        })
        assert "results" in result
        assert "count" in result
        assert "query_params" in result
        assert "data_version" in result
        assert result["suggestion"] is None


@pytest.mark.asyncio
class TestNearestPlace:
    """Tests for nearest_place_of_type against fixture data."""

    async def test_returns_one_result(self, test_registry):
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "coffee_shop",
        })
        assert result["count"] == 1

    async def test_correct_nearest(self, test_registry, known_nearest_coffee_shop):
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "coffee_shop",
        })
        nearest = result["results"][0]
        assert nearest["name"] == known_nearest_coffee_shop["name"]


@pytest.mark.asyncio
class TestCountPlaces:
    """Tests for count_places_by_type_in_radius against fixture data."""

    async def test_count_matches_search(self, test_registry, known_coffee_shops_within_500m):
        """Count should match the number of results from places_in_radius."""
        count_result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop",
        })
        assert count_result["results"][0]["count"] == known_coffee_shops_within_500m


@pytest.mark.asyncio
class TestGetPlaceCategories:
    """Tests for get_place_categories."""

    async def test_search_coffee(self, test_registry):
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "coffee",
        })
        categories = [c["category"] for c in result["results"]]
        assert "coffee_shop" in categories

    async def test_search_no_match(self, test_registry):
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "zzz_nonexistent_zzz",
        })
        assert result["count"] == 0

    async def test_no_query_returns_categories(self, test_registry):
        result = await execute_operation(test_registry, "get_place_categories", {})
        assert result["count"] > 0
