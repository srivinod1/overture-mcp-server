"""Unit tests for response envelope builder."""

import pytest
from overture_mcp.response import success_response, empty_response, error_response


class TestSuccessResponse:
    """Tests for success_response function."""

    def test_structure(self):
        resp = success_response(
            results=[{"name": "Cafe"}],
            query_params={"lat": 52.37},
            data_version="2026-01-21.0",
        )
        assert "results" in resp
        assert "count" in resp
        assert "query_params" in resp
        assert "data_version" in resp
        assert "suggestion" in resp

    def test_count_matches_results(self):
        results = [{"a": 1}, {"b": 2}, {"c": 3}]
        resp = success_response(
            results=results,
            query_params={},
            data_version="v1",
        )
        assert resp["count"] == 3

    def test_suggestion_null_when_results_exist(self):
        resp = success_response(
            results=[{"name": "Cafe"}],
            query_params={},
            data_version="v1",
            suggestion="This should be cleared",
        )
        assert resp["suggestion"] is None

    def test_suggestion_set_when_empty(self):
        resp = success_response(
            results=[],
            query_params={},
            data_version="v1",
            suggestion="Try a larger radius.",
        )
        assert resp["suggestion"] == "Try a larger radius."

    def test_query_params_echoed(self):
        params = {"lat": 52.3676, "lng": 4.9041, "radius_m": 500}
        resp = success_response(
            results=[],
            query_params=params,
            data_version="v1",
        )
        assert resp["query_params"] == params

    def test_data_version(self):
        resp = success_response(
            results=[],
            query_params={},
            data_version="2026-01-21.0",
        )
        assert resp["data_version"] == "2026-01-21.0"

    def test_empty_results_is_list(self):
        resp = success_response(
            results=[],
            query_params={},
            data_version="v1",
        )
        assert resp["results"] == []
        assert isinstance(resp["results"], list)

    def test_count_zero_when_empty(self):
        resp = success_response(
            results=[],
            query_params={},
            data_version="v1",
        )
        assert resp["count"] == 0


class TestEmptyResponse:
    """Tests for empty_response convenience function."""

    def test_results_empty_array(self):
        resp = empty_response(
            query_params={},
            data_version="v1",
            suggestion="Try larger radius.",
        )
        assert resp["results"] == []

    def test_count_is_zero(self):
        resp = empty_response(
            query_params={},
            data_version="v1",
            suggestion="hint",
        )
        assert resp["count"] == 0

    def test_suggestion_set(self):
        resp = empty_response(
            query_params={},
            data_version="v1",
            suggestion="No banks found within 500m.",
        )
        assert resp["suggestion"] == "No banks found within 500m."


class TestErrorResponse:
    """Tests for error_response function."""

    def test_structure(self):
        resp = error_response(
            error="Something went wrong",
            error_type="internal_error",
        )
        assert "error" in resp
        assert "error_type" in resp

    def test_validation_error(self):
        resp = error_response(
            error="lat must be between -90 and 90",
            error_type="validation_error",
            query_params={"lat": 200},
        )
        assert resp["error_type"] == "validation_error"
        assert resp["query_params"] == {"lat": 200}

    def test_query_timeout(self):
        resp = error_response(
            error="Query timeout after 30s",
            error_type="query_timeout",
        )
        assert resp["error_type"] == "query_timeout"

    def test_auth_error(self):
        resp = error_response(
            error="Invalid API key",
            error_type="auth_error",
        )
        assert resp["error_type"] == "auth_error"

    def test_internal_error(self):
        resp = error_response(
            error="Unexpected error",
            error_type="internal_error",
        )
        assert resp["error_type"] == "internal_error"

    def test_invalid_error_type(self):
        with pytest.raises(ValueError, match="Invalid error_type"):
            error_response(error="test", error_type="unknown_type")

    def test_query_params_optional(self):
        resp = error_response(
            error="test",
            error_type="internal_error",
        )
        assert "query_params" not in resp

    def test_query_params_included(self):
        resp = error_response(
            error="test",
            error_type="validation_error",
            query_params={"lat": 52.37},
        )
        assert resp["query_params"] == {"lat": 52.37}
