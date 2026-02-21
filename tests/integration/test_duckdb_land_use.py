"""Integration tests for land use queries against fixture data."""

import pytest
from overture_mcp.server import execute_operation


@pytest.mark.asyncio
class TestLandUseAtPoint:
    """Tests for land_use_at_point against fixture data."""

    async def test_finds_land_use_at_center(self, test_registry):
        """Amsterdam center should be inside at least one land use polygon."""
        result = await execute_operation(test_registry, "land_use_at_point", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert result["count"] > 0

    async def test_result_has_expected_fields(self, test_registry):
        result = await execute_operation(test_registry, "land_use_at_point", {
            "lat": 52.3676, "lng": 4.9041,
        })
        if result["count"] > 0:
            for r in result["results"]:
                assert "subtype" in r
                assert "class" in r
                assert "names_primary" in r
                assert "source" in r

    async def test_ocean_point_no_land_use(self, test_registry):
        """Gulf of Guinea should have no land use designation."""
        result = await execute_operation(test_registry, "land_use_at_point", {
            "lat": 0.0, "lng": 0.0,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None

    async def test_response_envelope(self, test_registry):
        result = await execute_operation(test_registry, "land_use_at_point", {
            "lat": 52.3676, "lng": 4.9041,
        })
        assert "results" in result
        assert "count" in result
        assert "query_params" in result
        assert "data_version" in result


@pytest.mark.asyncio
class TestLandUseComposition:
    """Tests for land_use_composition against fixture data."""

    async def test_returns_results(self, test_registry):
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        assert "error" not in result
        assert result["count"] == 1
        assert result["results"][0]["total_parcels"] > 0

    async def test_has_composition_breakdown(self, test_registry):
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        composition = result["results"][0]["composition"]
        assert isinstance(composition, dict)
        assert len(composition) > 0

    async def test_percentages_sum_to_100(self, test_registry):
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        composition = result["results"][0]["composition"]
        total_pct = sum(v["percentage"] for v in composition.values())
        assert abs(total_pct - 100.0) < 0.5

    async def test_counts_sum_to_total(self, test_registry):
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        data = result["results"][0]
        count_sum = sum(v["count"] for v in data["composition"].values())
        assert count_sum == data["total_parcels"]

    async def test_residential_present(self, test_registry):
        """Fixture data has 8 residential parcels near center."""
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
        })
        composition = result["results"][0]["composition"]
        assert "residential" in composition

    async def test_empty_area(self, test_registry):
        result = await execute_operation(test_registry, "land_use_composition", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500,
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None


@pytest.mark.asyncio
class TestLandUseSearch:
    """Tests for land_use_search against fixture data."""

    async def test_finds_residential_parcels(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000, "subtype": "residential",
        })
        assert result["count"] > 0
        for r in result["results"]:
            assert r["subtype"] == "residential"

    async def test_result_has_expected_fields(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000, "subtype": "residential",
        })
        for r in result["results"]:
            assert "subtype" in r
            assert "class" in r
            assert "names_primary" in r
            assert "lat" in r
            assert "lng" in r
            assert "distance_m" in r

    async def test_ordered_by_distance(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000, "subtype": "residential",
        })
        distances = [r["distance_m"] for r in result["results"]]
        assert distances == sorted(distances)

    async def test_respects_limit(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000,
            "subtype": "residential", "limit": 2,
        })
        assert result["count"] <= 2

    async def test_finds_park_parcels(self, test_registry):
        """Fixture has park parcels near center."""
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000, "subtype": "park",
        })
        assert result["count"] > 0
        for r in result["results"]:
            assert r["subtype"] == "park"

    async def test_invalid_subtype(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 1000, "subtype": "moonbase",
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    async def test_empty_area(self, test_registry):
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 0.0, "lng": 0.0, "radius_m": 500, "subtype": "residential",
        })
        assert result["count"] == 0
        assert result["suggestion"] is not None
