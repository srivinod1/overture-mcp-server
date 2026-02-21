"""Unit tests for transportation query builders.

Tests verify SQL structure, coordinate order, and parameterization.
No DuckDB execution — just string/param inspection.
"""

from overture_mcp.queries.transportation import (
    road_count_by_class_query,
    nearest_road_of_class_query,
    road_surface_composition_query,
)


class TestRoadCountByClassQuery:
    """Tests for road_count_by_class_query SQL generation."""

    def test_selects_class_and_count(self):
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "roads")
        assert "COALESCE(class, 'unknown') AS road_class" in sql
        assert "COUNT(*) AS count" in sql

    def test_groups_by_class(self):
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "roads")
        assert "GROUP BY COALESCE(class, 'unknown')" in sql

    def test_orders_by_count_desc(self):
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "roads")
        assert "ORDER BY count DESC" in sql

    def test_filters_to_road_subtype(self):
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "roads")
        assert "subtype = 'road'" in sql

    def test_uses_point_on_surface(self):
        """LineString geometry requires ST_PointOnSurface, not direct flip."""
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "roads")
        assert "ST_FlipCoordinates(ST_PointOnSurface(geometry))" in sql

    def test_has_bbox_prefilter(self):
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "roads")
        assert "bbox.xmin BETWEEN ? AND ?" in sql
        assert "bbox.ymin BETWEEN ? AND ?" in sql

    def test_coordinate_order(self):
        """ST_Point params should be (lng, lat)."""
        _, params = road_count_by_class_query(52.37, 4.90, 500, "roads")
        # After bbox params, next two are lng, lat for ST_Point
        assert params[4] == 4.90  # lng
        assert params[5] == 52.37  # lat

    def test_param_count(self):
        _, params = road_count_by_class_query(52.37, 4.90, 500, "roads")
        # lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m
        assert len(params) == 7

    def test_data_source_in_from(self):
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "my_roads")
        assert "FROM my_roads" in sql

    def test_no_limit(self):
        """Count-by-class should return all classes, no LIMIT."""
        sql, _ = road_count_by_class_query(52.37, 4.90, 500, "roads")
        assert "LIMIT" not in sql


class TestNearestRoadOfClassQuery:
    """Tests for nearest_road_of_class_query SQL generation."""

    def test_selects_core_columns(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert 'names."primary" AS name' in sql
        assert "class AS road_class" in sql
        assert "road_surface" in sql
        assert "distance_m" in sql

    def test_selects_road_flags(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert "is_bridge" in sql
        assert "is_tunnel" in sql
        assert "is_link" in sql

    def test_limit_one(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert "LIMIT 1" in sql

    def test_road_class_parameterized(self):
        sql, params = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert "residential" not in sql
        assert "residential" in params

    def test_uses_point_on_surface(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert "ST_FlipCoordinates(ST_PointOnSurface(geometry))" in sql

    def test_filters_to_road_subtype(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert "subtype = 'road'" in sql

    def test_include_geometry_false(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads", include_geometry=False)
        assert "ST_AsText" not in sql

    def test_include_geometry_true(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads", include_geometry=True)
        assert "ST_AsText(geometry) AS geometry" in sql

    def test_coordinate_order(self):
        """First two params should be lng, lat for ST_Point."""
        _, params = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert params[0] == 4.90   # lng
        assert params[1] == 52.37  # lat

    def test_param_count(self):
        _, params = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        # lng, lat (SELECT), lng_min, lng_max, lat_min, lat_max, road_class, lng, lat (WHERE), max_radius
        assert len(params) == 10

    def test_orders_by_distance(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert "ORDER BY distance_m ASC" in sql

    def test_has_bbox_prefilter(self):
        sql, _ = nearest_road_of_class_query(52.37, 4.90, "residential", "roads")
        assert "bbox.xmin BETWEEN ? AND ?" in sql
        assert "bbox.ymin BETWEEN ? AND ?" in sql


class TestRoadSurfaceCompositionQuery:
    """Tests for road_surface_composition_query SQL generation."""

    def test_selects_surface_and_count(self):
        sql, _ = road_surface_composition_query(52.37, 4.90, 500, "roads")
        assert "COALESCE(road_surface[1].value, 'unknown') AS surface_type" in sql
        assert "COUNT(*) AS count" in sql

    def test_groups_by_surface(self):
        sql, _ = road_surface_composition_query(52.37, 4.90, 500, "roads")
        assert "GROUP BY COALESCE(road_surface[1].value, 'unknown')" in sql

    def test_orders_by_count_desc(self):
        sql, _ = road_surface_composition_query(52.37, 4.90, 500, "roads")
        assert "ORDER BY count DESC" in sql

    def test_filters_to_road_subtype(self):
        sql, _ = road_surface_composition_query(52.37, 4.90, 500, "roads")
        assert "subtype = 'road'" in sql

    def test_uses_point_on_surface(self):
        sql, _ = road_surface_composition_query(52.37, 4.90, 500, "roads")
        assert "ST_FlipCoordinates(ST_PointOnSurface(geometry))" in sql

    def test_param_count(self):
        _, params = road_surface_composition_query(52.37, 4.90, 500, "roads")
        # Same as road_count: lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m
        assert len(params) == 7

    def test_no_limit(self):
        """Composition should return all surface types, no LIMIT."""
        sql, _ = road_surface_composition_query(52.37, 4.90, 500, "roads")
        assert "LIMIT" not in sql
