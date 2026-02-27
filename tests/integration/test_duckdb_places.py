"""Integration tests for places queries against fixture data."""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestPlacesInRadius:
    """Tests for places_in_radius against fixture data."""

    async def test_returns_correct_count(self, test_registry, known_cafes_within_500m):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert result["count"] == known_cafes_within_500m

    async def test_ordered_by_distance(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        distances = [r["distance_m"] for r in result["results"]]
        assert distances == sorted(distances)

    async def test_distance_accuracy(self, test_registry, known_nearest_cafe):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        nearest = result["results"][0]
        assert nearest["name"] == known_nearest_cafe["name"]
        # Allow 2m tolerance for spheroid vs fixture approximation
        assert abs(nearest["distance_m"] - known_nearest_cafe["distance_m"]) <= 2

    async def test_respects_limit(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
            "limit": 3,
        })
        assert result["count"] == 3

    async def test_excludes_outside_radius(self, test_registry):
        """400m radius should exclude cafes at 420m+."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 400, "category": "cafe",
        })
        for r in result["results"]:
            assert r["distance_m"] < 400

    async def test_result_has_required_fields(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        for r in result["results"]:
            assert "name" in r
            assert "category" in r
            assert "lat" in r
            assert "lng" in r
            assert "distance_m" in r
            # Enhanced fields
            assert "confidence" in r
            assert "address" in r  # may be None
            assert "phone" in r    # may be None
            assert "website" in r  # may be None
            assert "brand" in r    # may be None

    async def test_confidence_is_float(self, test_registry):
        """Confidence score should be a float between 0 and 1."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        for r in result["results"]:
            assert isinstance(r["confidence"], float)
            assert 0.0 <= r["confidence"] <= 1.0

    async def test_response_envelope(self, test_registry):
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert "results" in result
        assert "count" in result
        assert "query_params" in result
        assert "data_version" in result
        assert result["suggestion"] is None

    async def test_excludes_permanently_closed_by_default(self, test_registry):
        """Permanently closed places should be excluded by default."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        names = [r["name"] for r in result["results"]]
        assert "Mokum Cafe" not in names

    async def test_includes_temporarily_closed_by_default(self, test_registry):
        """Temporarily closed places should be included by default."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        names = [r["name"] for r in result["results"]]
        assert "Canal Cafe" in names

    async def test_include_closed_returns_all(
        self, test_registry, known_cafes_within_500m_including_closed,
    ):
        """include_closed=true should return permanently closed places too."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
            "include_closed": True,
        })
        assert result["count"] == known_cafes_within_500m_including_closed
        names = [r["name"] for r in result["results"]]
        assert "Mokum Cafe" in names


@pytest.mark.asyncio
class TestPlacesBrandAndAddress:
    """Tests for enhanced place fields: brand, address, phone, website."""

    async def test_branded_place_has_brand(self, test_registry):
        """Chain location should have brand info."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        branded = [r for r in result["results"] if r["name"] == "Brew & Co. Dam Square"]
        assert len(branded) == 1
        brand = branded[0]["brand"]
        assert brand is not None
        assert brand["name"] == "Brew & Co."
        assert brand["wikidata"] == "Q99999999"

    async def test_unbranded_place_has_null_brand(self, test_registry):
        """Non-chain cafes should have null brand."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        koffie = [r for r in result["results"] if r["name"] == "Cafe Centrum"]
        assert len(koffie) == 1
        assert koffie[0]["brand"] is None

    async def test_place_with_freeform_address(self, test_registry):
        """Places with freeform address should return it."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        # Cafe Centrum has freeform address "Damrak 1, 1012 LG Amsterdam"
        koffie = [r for r in result["results"] if r["name"] == "Cafe Centrum"]
        assert len(koffie) == 1
        assert koffie[0]["address"] is not None
        assert "Damrak" in koffie[0]["address"]

    async def test_place_with_website(self, test_registry):
        """First cafe should have a website."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        # Cafe Centrum (idx 0) has a website
        koffie = [r for r in result["results"] if r["name"] == "Cafe Centrum"]
        assert len(koffie) == 1
        assert koffie[0]["website"] is not None
        assert "example.com" in koffie[0]["website"]

    async def test_place_with_phone(self, test_registry):
        """First cafe should have a phone."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        koffie = [r for r in result["results"] if r["name"] == "Cafe Centrum"]
        assert len(koffie) == 1
        assert koffie[0]["phone"] is not None
        assert "+31" in koffie[0]["phone"]


@pytest.mark.asyncio
class TestNearestPlace:
    """Tests for nearest_place_of_type against fixture data."""

    async def test_returns_one_result(self, test_registry):
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        assert result["count"] == 1

    async def test_correct_nearest(self, test_registry, known_nearest_cafe):
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        nearest = result["results"][0]
        assert nearest["name"] == known_nearest_cafe["name"]

    async def test_nearest_has_enhanced_fields(self, test_registry):
        """Nearest place result should have confidence, address, brand etc."""
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        nearest = result["results"][0]
        assert "confidence" in nearest
        assert "address" in nearest
        assert "phone" in nearest
        assert "website" in nearest
        assert "brand" in nearest

    async def test_nearest_excludes_permanently_closed(self, test_registry):
        """nearest_place_of_type should exclude permanently closed by default."""
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041, "category": "cafe",
        })
        # The nearest should not be a permanently_closed place
        assert result["results"][0]["name"] != "Mokum Cafe"


@pytest.mark.asyncio
class TestCountPlaces:
    """Tests for count_places_by_type_in_radius against fixture data."""

    async def test_count_matches_search(self, test_registry, known_cafes_within_500m):
        """Count should match the number of results from places_in_radius."""
        count_result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert count_result["results"][0]["count"] == known_cafes_within_500m

    async def test_count_with_include_closed(
        self, test_registry, known_cafes_within_500m_including_closed,
    ):
        """Count with include_closed=true should include permanently closed."""
        count_result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe",
            "include_closed": True,
        })
        assert count_result["results"][0]["count"] == known_cafes_within_500m_including_closed


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
