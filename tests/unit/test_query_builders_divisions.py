"""Unit tests for divisions query builders."""

import pytest
from overture_mcp.queries.divisions import point_in_boundary_query


class TestPointInBoundaryQuery:
    """Tests for point_in_boundary_query SQL generation."""

    def test_uses_st_contains(self):
        sql, _ = point_in_boundary_query(52.37, 4.90, "divisions")
        assert "ST_Contains(geometry, ST_Point(?, ?))" in sql

    def test_no_flip_coordinates(self):
        """ST_Contains does NOT need ST_FlipCoordinates."""
        sql, _ = point_in_boundary_query(52.37, 4.90, "divisions")
        assert "ST_FlipCoordinates" not in sql

    def test_no_st_distance(self):
        """Divisions use containment, not distance."""
        sql, _ = point_in_boundary_query(52.37, 4.90, "divisions")
        assert "ST_Distance" not in sql

    def test_bbox_containment_filter(self):
        """Bbox uses <= / >= for containment, not BETWEEN."""
        sql, _ = point_in_boundary_query(52.37, 4.90, "divisions")
        assert "bbox.xmin <= ?" in sql
        assert "bbox.xmax >= ?" in sql
        assert "bbox.ymin <= ?" in sql
        assert "bbox.ymax >= ?" in sql

    def test_order_by_admin_level(self):
        sql, _ = point_in_boundary_query(52.37, 4.90, "divisions")
        assert "ORDER BY admin_level ASC" in sql

    def test_selects_name_level_subtype(self):
        sql, _ = point_in_boundary_query(52.37, 4.90, "divisions")
        assert 'names."primary" AS name' in sql
        assert "admin_level" in sql
        assert "subtype" in sql

    def test_coordinate_order_in_params(self):
        """Verify bbox params are lng, lng, lat, lat; ST_Point is lng, lat."""
        sql, params = point_in_boundary_query(52.37, 4.90, "divisions")
        # bbox: xmin <= lng, xmax >= lng, ymin <= lat, ymax >= lat
        assert params[0] == 4.90  # lng for bbox.xmin
        assert params[1] == 4.90  # lng for bbox.xmax
        assert params[2] == 52.37  # lat for bbox.ymin
        assert params[3] == 52.37  # lat for bbox.ymax
        # ST_Point(lng, lat)
        assert params[4] == 4.90  # lng
        assert params[5] == 52.37  # lat

    def test_no_limit(self):
        """Should return all matching boundaries."""
        sql, _ = point_in_boundary_query(52.37, 4.90, "divisions")
        assert "LIMIT" not in sql
