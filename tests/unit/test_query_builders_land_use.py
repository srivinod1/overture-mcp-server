"""Unit tests for land use query builders.

Tests verify SQL structure, coordinate order, and parameterization.
No DuckDB execution — just string/param inspection.
"""

from overture_mcp.queries.land_use import (
    land_use_at_point_query,
    land_use_composition_query,
    land_use_search_query,
)


class TestLandUseAtPointQuery:
    """Tests for land_use_at_point_query SQL generation."""

    def test_selects_expected_columns(self):
        sql, _ = land_use_at_point_query(52.37, 4.90, "land_use")
        assert "subtype" in sql
        assert "class" in sql
        assert 'names."primary" AS names_primary' in sql
        assert "source" in sql

    def test_uses_st_contains(self):
        """Point-in-polygon uses ST_Contains, not ST_Distance."""
        sql, _ = land_use_at_point_query(52.37, 4.90, "land_use")
        assert "ST_Contains(geometry, ST_Point(?, ?))" in sql

    def test_no_st_flip_coordinates(self):
        """ST_Contains works in coordinate space, no flip needed."""
        sql, _ = land_use_at_point_query(52.37, 4.90, "land_use")
        assert "ST_FlipCoordinates" not in sql

    def test_no_st_distance(self):
        """Point-in-polygon query should not use distance."""
        sql, _ = land_use_at_point_query(52.37, 4.90, "land_use")
        assert "ST_Distance_Spheroid" not in sql

    def test_bbox_prefilter(self):
        """Should use bbox for quick elimination."""
        sql, _ = land_use_at_point_query(52.37, 4.90, "land_use")
        assert "bbox.xmin <= ?" in sql
        assert "bbox.xmax >= ?" in sql
        assert "bbox.ymin <= ?" in sql
        assert "bbox.ymax >= ?" in sql

    def test_coordinate_order_st_point(self):
        """ST_Point must receive (lng, lat)."""
        _, params = land_use_at_point_query(52.37, 4.90, "land_use")
        # Last two params are lng, lat for ST_Point in ST_Contains
        assert params[-2] == 4.90   # lng
        assert params[-1] == 52.37  # lat

    def test_param_count(self):
        _, params = land_use_at_point_query(52.37, 4.90, "land_use")
        # lng, lng (bbox x), lat, lat (bbox y), lng, lat (ST_Point)
        assert len(params) == 6

    def test_data_source_in_from(self):
        sql, _ = land_use_at_point_query(52.37, 4.90, "my_land_use")
        assert "FROM my_land_use" in sql

    def test_no_limit(self):
        """Should return all matching polygons at the point."""
        sql, _ = land_use_at_point_query(52.37, 4.90, "land_use")
        assert "LIMIT" not in sql


class TestLandUseCompositionQuery:
    """Tests for land_use_composition_query SQL generation."""

    def test_selects_subtype_and_count(self):
        sql, _ = land_use_composition_query(52.37, 4.90, 500, "land_use")
        assert "subtype" in sql
        assert "COUNT(*) AS count" in sql

    def test_groups_by_subtype(self):
        sql, _ = land_use_composition_query(52.37, 4.90, 500, "land_use")
        assert "GROUP BY subtype" in sql

    def test_orders_by_count_desc(self):
        sql, _ = land_use_composition_query(52.37, 4.90, 500, "land_use")
        assert "ORDER BY count DESC" in sql

    def test_uses_centroid_pattern(self):
        """Land use polygons should use ST_Centroid(geometry)."""
        sql, _ = land_use_composition_query(52.37, 4.90, 500, "land_use")
        assert "ST_FlipCoordinates(ST_Centroid(geometry))" in sql

    def test_has_bbox_prefilter(self):
        sql, _ = land_use_composition_query(52.37, 4.90, 500, "land_use")
        assert "bbox.xmin BETWEEN ? AND ?" in sql
        assert "bbox.ymin BETWEEN ? AND ?" in sql

    def test_param_count(self):
        _, params = land_use_composition_query(52.37, 4.90, 500, "land_use")
        # lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m
        assert len(params) == 7

    def test_no_limit(self):
        sql, _ = land_use_composition_query(52.37, 4.90, 500, "land_use")
        assert "LIMIT" not in sql


class TestLandUseSearchQuery:
    """Tests for land_use_search_query SQL generation."""

    def test_selects_expected_columns(self):
        sql, _ = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        assert "subtype" in sql
        assert "class" in sql
        assert 'names."primary" AS names_primary' in sql
        assert "distance_m" in sql

    def test_uses_centroid_for_lat_lng(self):
        """Lat/lng should be centroid of polygon, not raw geometry."""
        sql, _ = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        assert "ST_Y(ST_Centroid(geometry)) AS lat" in sql
        assert "ST_X(ST_Centroid(geometry)) AS lng" in sql

    def test_uses_centroid_for_distance(self):
        sql, _ = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        assert "ST_FlipCoordinates(ST_Centroid(geometry))" in sql

    def test_subtype_parameterized(self):
        sql, params = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        assert "residential" not in sql
        assert "residential" in params

    def test_has_limit(self):
        sql, params = land_use_search_query(52.37, 4.90, 500, "residential", "land_use", limit=10)
        assert "LIMIT ?" in sql
        assert 10 in params

    def test_include_geometry_false(self):
        sql, _ = land_use_search_query(52.37, 4.90, 500, "residential", "land_use", include_geometry=False)
        assert "ST_AsText" not in sql

    def test_include_geometry_true(self):
        sql, _ = land_use_search_query(52.37, 4.90, 500, "residential", "land_use", include_geometry=True)
        assert "ST_AsText(geometry) AS geometry" in sql

    def test_has_bbox_prefilter(self):
        sql, _ = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        assert "bbox.xmin BETWEEN ? AND ?" in sql
        assert "bbox.ymin BETWEEN ? AND ?" in sql

    def test_orders_by_distance(self):
        sql, _ = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        assert "ORDER BY distance_m ASC" in sql

    def test_coordinate_order(self):
        """First two params should be lng, lat for ST_Point."""
        _, params = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        assert params[0] == 4.90   # lng
        assert params[1] == 52.37  # lat

    def test_param_count(self):
        _, params = land_use_search_query(52.37, 4.90, 500, "residential", "land_use")
        # lng, lat (SELECT), lng_min, lng_max, lat_min, lat_max, subtype, lng, lat (WHERE), radius_m, limit
        assert len(params) == 11
