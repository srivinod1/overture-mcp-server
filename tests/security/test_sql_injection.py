"""
Security tests: SQL injection prevention.

These tests verify that malicious SQL payloads are rejected at the
validation layer and never reach the SQL query builder. Our defense-in-depth
strategy has two layers:

1. Category validation: category values must exist in the cached taxonomy
2. Parameterized queries: all user-provided values use ? placeholders

These tests verify layer 1 (validation rejection). Layer 2 is verified
implicitly by all integration tests that successfully pass data through
to DuckDB without SQL errors.
"""

import pytest
from overture_mcp.server import execute_operation
from overture_mcp.validation import (
    ValidationError,
    validate_category,
    validate_land_use_subtype,
    validate_road_class,
)


class TestCategoryInjection:
    """SQL injection payloads in the category parameter."""

    INJECTION_PAYLOADS = [
        # Classic SQL injection
        "'; DROP TABLE places; --",
        "' OR '1'='1",
        "' OR 1=1 --",
        "'; SELECT * FROM information_schema.tables --",
        # UNION injection
        "x' UNION SELECT * FROM information_schema.tables --",
        "coffee_shop' UNION ALL SELECT 1,2,3,4,5 --",
        # Stacked queries
        "coffee_shop; DROP TABLE places",
        "coffee_shop; INSERT INTO places VALUES(1,2,3)",
        # Comment injection
        "coffee_shop/**/OR/**/1=1",
        "coffee_shop'--",
        # Hex / encoded
        "0x636f666665655f73686f70",
        # Null byte
        "coffee_shop\x00' OR '1'='1",
        # Backtick escape
        "`coffee_shop`; DROP TABLE places",
        # Double-encode
        "%27%20OR%20%271%27%3D%271",
    ]

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_category_validation_rejects_injection(self, payload, category_names):
        """All injection payloads should be rejected by validate_category."""
        with pytest.raises(ValidationError) as exc_info:
            validate_category(payload, category_names)
        assert "Unknown category" in exc_info.value.message

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS[:5])
    @pytest.mark.asyncio
    async def test_places_operation_rejects_injection(self, test_registry, payload):
        """Injection payloads through the full operation pipeline should fail."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": payload,
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS[:5])
    @pytest.mark.asyncio
    async def test_count_operation_rejects_injection(self, test_registry, payload):
        """Count operation should also reject injection payloads."""
        result = await execute_operation(test_registry, "count_places_by_type_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": payload,
        })
        assert "error" in result

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS[:5])
    @pytest.mark.asyncio
    async def test_nearest_operation_rejects_injection(self, test_registry, payload):
        """Nearest operation should also reject injection payloads."""
        result = await execute_operation(test_registry, "nearest_place_of_type", {
            "lat": 52.3676, "lng": 4.9041,
            "category": payload,
        })
        assert "error" in result


class TestQueryParameterInjection:
    """SQL injection payloads in the query parameter for category search."""

    QUERY_PAYLOADS = [
        "'; DROP TABLE categories; --",
        "' UNION SELECT * FROM pg_tables --",
        "coffee'; exec xp_cmdshell('dir') --",
    ]

    @pytest.mark.parametrize("payload", QUERY_PAYLOADS)
    @pytest.mark.asyncio
    async def test_category_search_handles_injection(self, test_registry, payload):
        """Category search should safely handle injection payloads.

        The query parameter is used for in-memory string matching, not SQL.
        It should simply return no results (no match in taxonomy).
        """
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": payload,
        })
        # Should not crash — just no matching categories
        assert "error" not in result
        assert result["count"] == 0


class TestNumericInjection:
    """Attempt to inject through numeric parameters."""

    @pytest.mark.asyncio
    async def test_string_in_lat(self, test_registry):
        """String value for lat should be rejected at validation."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": "52.3676; DROP TABLE buildings",
            "lng": 4.9041,
            "radius_m": 500,
        })
        assert "error" in result

    @pytest.mark.asyncio
    async def test_string_in_radius(self, test_registry):
        """String value for radius should be rejected at validation."""
        result = await execute_operation(test_registry, "building_count_in_radius", {
            "lat": 52.3676,
            "lng": 4.9041,
            "radius_m": "500; DROP TABLE buildings",
        })
        assert "error" in result

    @pytest.mark.asyncio
    async def test_string_in_limit(self, test_registry):
        """String value for limit should be rejected at validation."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "category": "coffee_shop",
            "limit": "20; DROP TABLE places",
        })
        assert "error" in result


class TestRoadClassInjection:
    """SQL injection payloads in the road_class parameter."""

    INJECTION_PAYLOADS = [
        "'; DROP TABLE roads; --",
        "' OR '1'='1",
        "residential' UNION SELECT * FROM information_schema.tables --",
        "residential; INSERT INTO roads VALUES(1,2,3)",
        "residential/**/OR/**/1=1",
    ]

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_road_class_validation_rejects_injection(self, payload):
        """All injection payloads should be rejected by validate_road_class."""
        with pytest.raises(ValidationError) as exc_info:
            validate_road_class(payload)
        assert "Unknown road_class" in exc_info.value.message

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    @pytest.mark.asyncio
    async def test_nearest_road_rejects_injection(self, test_registry, payload):
        """nearest_road_of_class should reject injection payloads."""
        result = await execute_operation(test_registry, "nearest_road_of_class", {
            "lat": 52.3676, "lng": 4.9041,
            "road_class": payload,
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"


class TestLandUseSubtypeInjection:
    """SQL injection payloads in the land use subtype parameter."""

    INJECTION_PAYLOADS = [
        "'; DROP TABLE land_use; --",
        "' OR '1'='1",
        "residential' UNION SELECT * FROM information_schema.tables --",
        "park; DELETE FROM land_use",
    ]

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_subtype_validation_rejects_injection(self, payload):
        """All injection payloads should be rejected by validate_land_use_subtype."""
        with pytest.raises(ValidationError) as exc_info:
            validate_land_use_subtype(payload)
        assert "Unknown land use subtype" in exc_info.value.message

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    @pytest.mark.asyncio
    async def test_land_use_search_rejects_injection(self, test_registry, payload):
        """land_use_search should reject injection payloads."""
        result = await execute_operation(test_registry, "land_use_search", {
            "lat": 52.3676, "lng": 4.9041, "radius_m": 500,
            "subtype": payload,
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"
