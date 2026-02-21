"""
Compatibility tests: verify all operations behave consistently.

In both direct and progressive tool modes, the same execute_operation()
function is used. These tests ensure every operation produces consistent
results when called with identical parameters, and that the response
envelope structure is uniform across all operations.
"""

import pytest
from overture_mcp.server import execute_operation


# All operations with valid params for Amsterdam center
ALL_OPERATIONS = [
    ("get_place_categories", {"query": "coffee"}),
    ("places_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop"}),
    ("nearest_place_of_type", {"lat": 52.3676, "lng": 4.9041, "category": "coffee_shop"}),
    ("count_places_by_type_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop"}),
    ("building_count_in_radius", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500}),
    ("building_class_composition", {"lat": 52.3676, "lng": 4.9041, "radius_m": 500}),
    ("point_in_admin_boundary", {"lat": 52.3676, "lng": 4.9041}),
]


@pytest.mark.asyncio
class TestResponseEnvelopeConsistency:
    """Every successful response should have the same envelope structure."""

    @pytest.mark.parametrize("op_name,params", ALL_OPERATIONS)
    async def test_envelope_has_required_keys(self, test_registry, op_name, params):
        """All responses must have results, count, query_params, data_version, suggestion."""
        result = await execute_operation(test_registry, op_name, params)
        assert "results" in result, f"{op_name}: missing 'results'"
        assert "count" in result, f"{op_name}: missing 'count'"
        assert "query_params" in result, f"{op_name}: missing 'query_params'"
        assert "data_version" in result, f"{op_name}: missing 'data_version'"
        assert "suggestion" in result, f"{op_name}: missing 'suggestion'"

    @pytest.mark.parametrize("op_name,params", ALL_OPERATIONS)
    async def test_results_is_list(self, test_registry, op_name, params):
        """results field should always be a list."""
        result = await execute_operation(test_registry, op_name, params)
        assert isinstance(result["results"], list), f"{op_name}: results is not a list"

    @pytest.mark.parametrize("op_name,params", ALL_OPERATIONS)
    async def test_count_matches_results_length(self, test_registry, op_name, params):
        """count should match len(results)."""
        result = await execute_operation(test_registry, op_name, params)
        assert result["count"] == len(result["results"]), (
            f"{op_name}: count={result['count']} != len(results)={len(result['results'])}"
        )

    @pytest.mark.parametrize("op_name,params", ALL_OPERATIONS)
    async def test_data_version_present(self, test_registry, op_name, params):
        """data_version should be a non-empty string."""
        result = await execute_operation(test_registry, op_name, params)
        assert isinstance(result["data_version"], str)
        assert len(result["data_version"]) > 0


@pytest.mark.asyncio
class TestIdempotency:
    """Same operation with same params should produce identical results."""

    @pytest.mark.parametrize("op_name,params", ALL_OPERATIONS)
    async def test_same_params_same_results(self, test_registry, op_name, params):
        """Calling the same operation twice should yield identical results."""
        result1 = await execute_operation(test_registry, op_name, params)
        result2 = await execute_operation(test_registry, op_name, params)
        assert result1 == result2, f"{op_name}: results differ between calls"


@pytest.mark.asyncio
class TestErrorEnvelopeConsistency:
    """Error responses should also have a consistent structure."""

    ERROR_CASES = [
        ("places_in_radius", {"lat": "invalid"}),
        ("building_count_in_radius", {"lat": 91, "lng": 0, "radius_m": 500}),
        ("does_not_exist", {}),
    ]

    @pytest.mark.parametrize("op_name,params", ERROR_CASES)
    async def test_error_has_required_keys(self, test_registry, op_name, params):
        """Error responses must have error and error_type."""
        result = await execute_operation(test_registry, op_name, params)
        assert "error" in result, f"{op_name}: missing 'error'"
        assert "error_type" in result, f"{op_name}: missing 'error_type'"

    @pytest.mark.parametrize("op_name,params", ERROR_CASES)
    async def test_error_type_is_string(self, test_registry, op_name, params):
        result = await execute_operation(test_registry, op_name, params)
        assert isinstance(result["error_type"], str)
