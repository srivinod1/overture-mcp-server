"""Unit tests for places query builders.

Tests verify SQL structure, coordinate order, and parameterization.
No DuckDB execution — just string/param inspection.
"""

import pytest
from overture_mcp.queries.places import (
    places_in_radius_query,
    nearest_place_query,
    count_places_query,
)


class TestPlacesInRadiusQuery:
    """Tests for places_in_radius_query SQL generation."""

    def test_sql_has_select_columns(self):
        sql, _ = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places")
        assert 'names."primary" AS name' in sql
        assert 'categories."primary" AS category' in sql
        assert "ST_Y(geometry) AS lat" in sql
        assert "ST_X(geometry) AS lng" in sql
        assert "distance_m" in sql

    def test_coordinate_order_st_point(self):
        """ST_Point must receive (lng, lat) — X before Y."""
        sql, params = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places")
        # The first two params are lng, lat for ST_Point
        assert params[0] == 4.90, "First ST_Point param should be lng"
        assert params[1] == 52.37, "Second ST_Point param should be lat"

    def test_uses_flip_coordinates(self):
        """ST_Distance_Spheroid must wrap args in ST_FlipCoordinates."""
        sql, _ = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places")
        assert "ST_FlipCoordinates(geometry)" in sql
        assert "ST_FlipCoordinates(ST_Point(?, ?))" in sql

    def test_category_parameterized(self):
        """Category must be a ? placeholder, not string interpolation."""
        sql, params = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places")
        # Category should be in params, not in SQL text
        assert "coffee_shop" not in sql
        assert "coffee_shop" in params

    def test_has_bbox_prefilter(self):
        sql, _ = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places")
        assert "bbox.xmin BETWEEN ? AND ?" in sql
        assert "bbox.ymin BETWEEN ? AND ?" in sql

    def test_has_order_by_distance(self):
        sql, _ = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places")
        assert "ORDER BY distance_m ASC" in sql

    def test_has_limit(self):
        sql, params = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places", limit=10)
        assert "LIMIT ?" in sql
        assert 10 in params

    def test_include_geometry_false(self):
        sql, _ = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places", include_geometry=False)
        assert "ST_AsText" not in sql

    def test_include_geometry_true(self):
        sql, _ = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places", include_geometry=True)
        assert "ST_AsText(geometry) AS geometry" in sql

    def test_data_source_in_from(self):
        sql, _ = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "my_table")
        assert "FROM my_table" in sql

    def test_param_count(self):
        """Verify correct number of parameters."""
        _, params = places_in_radius_query(52.37, 4.90, 500, "coffee_shop", "places", limit=20)
        # lng, lat (select), lng_min, lng_max, lat_min, lat_max, lng, lat (where), radius, category, limit
        assert len(params) == 11


class TestNearestPlaceQuery:
    """Tests for nearest_place_query SQL generation."""

    def test_limit_one(self):
        sql, params = nearest_place_query(52.37, 4.90, "atm", "places")
        assert "LIMIT ?" in sql
        # The limit param should be 1
        assert params[-1] == 1

    def test_uses_flip_coordinates(self):
        sql, _ = nearest_place_query(52.37, 4.90, "atm", "places")
        assert "ST_FlipCoordinates" in sql


class TestCountPlacesQuery:
    """Tests for count_places_query SQL generation."""

    def test_uses_count(self):
        sql, _ = count_places_query(52.37, 4.90, 500, "restaurant", "places")
        assert "COUNT(*) AS count" in sql

    def test_no_name_or_lat_columns(self):
        """Count query should not include name, lat, lng columns."""
        sql, _ = count_places_query(52.37, 4.90, 500, "restaurant", "places")
        assert "AS name" not in sql
        assert "AS lat" not in sql
        assert "AS lng" not in sql

    def test_no_limit(self):
        """Count query should not have LIMIT."""
        sql, _ = count_places_query(52.37, 4.90, 500, "restaurant", "places")
        assert "LIMIT" not in sql

    def test_no_order_by(self):
        """Count query should not have ORDER BY."""
        sql, _ = count_places_query(52.37, 4.90, 500, "restaurant", "places")
        assert "ORDER BY" not in sql

    def test_category_parameterized(self):
        sql, params = count_places_query(52.37, 4.90, 500, "restaurant", "places")
        assert "restaurant" not in sql
        assert "restaurant" in params
