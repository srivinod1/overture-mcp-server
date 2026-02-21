"""Unit tests for parameter validation."""

import math
import pytest
from overture_mcp.validation import (
    ValidationError,
    validate_lat,
    validate_lng,
    validate_radius,
    validate_limit,
    validate_category,
    validate_include_geometry,
    validate_query,
)


SAMPLE_CATEGORIES = {"coffee_shop", "restaurant", "bank", "hospital", "atm"}


class TestValidateLat:
    """Tests for latitude validation."""

    def test_valid_range(self):
        assert validate_lat(52.3676) == 52.3676

    def test_exactly_90(self):
        assert validate_lat(90.0) == 90.0

    def test_exactly_negative_90(self):
        assert validate_lat(-90.0) == -90.0

    def test_zero(self):
        assert validate_lat(0) == 0.0

    def test_below_min(self):
        with pytest.raises(ValidationError, match="must be between -90 and 90"):
            validate_lat(-90.001)

    def test_above_max(self):
        with pytest.raises(ValidationError, match="must be between -90 and 90"):
            validate_lat(90.001)

    def test_string_input(self):
        with pytest.raises(ValidationError, match="must be a number"):
            validate_lat("abc")

    def test_none_input(self):
        with pytest.raises(ValidationError, match="must be a number"):
            validate_lat(None)

    def test_nan_input(self):
        with pytest.raises(ValidationError, match="must be a finite number"):
            validate_lat(float("nan"))

    def test_inf_input(self):
        with pytest.raises(ValidationError, match="must be a finite number"):
            validate_lat(float("inf"))

    def test_negative_inf_input(self):
        with pytest.raises(ValidationError, match="must be a finite number"):
            validate_lat(float("-inf"))

    def test_string_number(self):
        """Numeric string should be accepted (agent might pass string)."""
        assert validate_lat("52.3676") == 52.3676

    def test_integer_input(self):
        assert validate_lat(52) == 52.0


class TestValidateLng:
    """Tests for longitude validation."""

    def test_valid_range(self):
        assert validate_lng(4.9041) == 4.9041

    def test_exactly_180(self):
        assert validate_lng(180.0) == 180.0

    def test_exactly_negative_180(self):
        assert validate_lng(-180.0) == -180.0

    def test_below_min(self):
        with pytest.raises(ValidationError, match="must be between -180 and 180"):
            validate_lng(-180.001)

    def test_above_max(self):
        with pytest.raises(ValidationError, match="must be between -180 and 180"):
            validate_lng(180.001)

    def test_string_input(self):
        with pytest.raises(ValidationError, match="must be a number"):
            validate_lng("abc")

    def test_nan_input(self):
        with pytest.raises(ValidationError, match="must be a finite number"):
            validate_lng(float("nan"))

    def test_inf_input(self):
        with pytest.raises(ValidationError, match="must be a finite number"):
            validate_lng(float("inf"))


class TestValidateRadius:
    """Tests for radius validation."""

    def test_valid_range(self):
        assert validate_radius(500, max_radius_m=50000) == 500

    def test_minimum(self):
        assert validate_radius(1, max_radius_m=50000) == 1

    def test_maximum(self):
        assert validate_radius(50000, max_radius_m=50000) == 50000

    def test_zero(self):
        with pytest.raises(ValidationError, match="must be between 1 and"):
            validate_radius(0, max_radius_m=50000)

    def test_negative(self):
        with pytest.raises(ValidationError, match="must be between 1 and"):
            validate_radius(-100, max_radius_m=50000)

    def test_above_max(self):
        with pytest.raises(ValidationError, match="must be between 1 and"):
            validate_radius(50001, max_radius_m=50000)

    def test_float_input(self):
        """Float is truncated to int."""
        assert validate_radius(500.7, max_radius_m=50000) == 500

    def test_string_number(self):
        assert validate_radius("500", max_radius_m=50000) == 500

    def test_string_input(self):
        with pytest.raises(ValidationError, match="must be a number"):
            validate_radius("abc", max_radius_m=50000)


class TestValidateLimit:
    """Tests for limit validation."""

    def test_valid_range(self):
        assert validate_limit(20) == 20

    def test_minimum(self):
        assert validate_limit(1) == 1

    def test_maximum(self):
        assert validate_limit(100) == 100

    def test_default_when_none(self):
        assert validate_limit(None) == 20

    def test_zero(self):
        with pytest.raises(ValidationError, match="must be between 1 and"):
            validate_limit(0)

    def test_above_max(self):
        with pytest.raises(ValidationError, match="must be between 1 and"):
            validate_limit(101)

    def test_custom_max(self):
        assert validate_limit(50, max_results=50) == 50
        with pytest.raises(ValidationError):
            validate_limit(51, max_results=50)


class TestValidateCategory:
    """Tests for category validation."""

    def test_valid_category(self):
        assert validate_category("coffee_shop", SAMPLE_CATEGORIES) == "coffee_shop"

    def test_unknown_category(self):
        with pytest.raises(ValidationError, match="Unknown category"):
            validate_category("nonexistent", SAMPLE_CATEGORIES)

    def test_empty_string(self):
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_category("", SAMPLE_CATEGORIES)

    def test_none(self):
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_category(None, SAMPLE_CATEGORIES)

    def test_whitespace_only(self):
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_category("   ", SAMPLE_CATEGORIES)

    def test_strips_whitespace(self):
        assert validate_category(" coffee_shop ", SAMPLE_CATEGORIES) == "coffee_shop"

    def test_sql_injection_payload(self):
        with pytest.raises(ValidationError, match="Unknown category"):
            validate_category("'; DROP TABLE places; --", SAMPLE_CATEGORIES)

    def test_union_injection_payload(self):
        with pytest.raises(ValidationError, match="Unknown category"):
            validate_category("x' UNION SELECT * FROM information_schema.tables --", SAMPLE_CATEGORIES)


class TestValidateIncludeGeometry:
    """Tests for include_geometry validation."""

    def test_none_returns_false(self):
        assert validate_include_geometry(None) is False

    def test_true(self):
        assert validate_include_geometry(True) is True

    def test_false(self):
        assert validate_include_geometry(False) is False

    def test_string_true(self):
        assert validate_include_geometry("true") is True

    def test_string_false(self):
        assert validate_include_geometry("false") is False


class TestValidateQuery:
    """Tests for query parameter validation."""

    def test_valid_string(self):
        assert validate_query("coffee") == "coffee"

    def test_none_returns_none(self):
        assert validate_query(None) is None

    def test_empty_string_returns_none(self):
        assert validate_query("") is None

    def test_whitespace_only_returns_none(self):
        assert validate_query("   ") is None

    def test_strips_whitespace(self):
        assert validate_query("  coffee  ") == "coffee"

    def test_non_string_raises(self):
        with pytest.raises(ValidationError, match="must be a string"):
            validate_query(123)
