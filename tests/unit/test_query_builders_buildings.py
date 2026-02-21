"""Unit tests for buildings query builders."""

import pytest
from overture_mcp.queries.buildings import (
    building_count_query,
    building_composition_query,
)


class TestBuildingCountQuery:
    """Tests for building_count_query SQL generation."""

    def test_uses_count(self):
        sql, _ = building_count_query(52.37, 4.90, 1000, "buildings")
        assert "COUNT(*) AS count" in sql

    def test_has_bbox_prefilter(self):
        sql, _ = building_count_query(52.37, 4.90, 1000, "buildings")
        assert "bbox.xmin BETWEEN ? AND ?" in sql
        assert "bbox.ymin BETWEEN ? AND ?" in sql

    def test_uses_centroid_and_flip_coordinates(self):
        """Buildings have polygon geometry; must use ST_Centroid before ST_FlipCoordinates."""
        sql, _ = building_count_query(52.37, 4.90, 1000, "buildings")
        assert "ST_FlipCoordinates(ST_Centroid(geometry))" in sql
        assert "ST_FlipCoordinates(ST_Point(?, ?))" in sql

    def test_no_category_filter(self):
        """Buildings don't have category filters."""
        sql, _ = building_count_query(52.37, 4.90, 1000, "buildings")
        assert "categories" not in sql

    def test_no_class_filter(self):
        """Count counts all buildings regardless of class."""
        sql, _ = building_count_query(52.37, 4.90, 1000, "buildings")
        assert "class" not in sql.lower() or "building_class" not in sql

    def test_data_source(self):
        sql, _ = building_count_query(52.37, 4.90, 1000, "my_buildings")
        assert "FROM my_buildings" in sql


class TestBuildingCompositionQuery:
    """Tests for building_composition_query SQL generation."""

    def test_group_by_coalesce(self):
        sql, _ = building_composition_query(52.37, 4.90, 1000, "buildings")
        assert "COALESCE(class, 'unknown')" in sql
        assert "GROUP BY COALESCE(class, 'unknown')" in sql

    def test_order_by_count_desc(self):
        sql, _ = building_composition_query(52.37, 4.90, 1000, "buildings")
        assert "ORDER BY count DESC" in sql

    def test_uses_centroid_and_flip_coordinates(self):
        """Buildings have polygon geometry; must use ST_Centroid before ST_FlipCoordinates."""
        sql, _ = building_composition_query(52.37, 4.90, 1000, "buildings")
        assert "ST_FlipCoordinates(ST_Centroid(geometry))" in sql

    def test_has_bbox_prefilter(self):
        sql, _ = building_composition_query(52.37, 4.90, 1000, "buildings")
        assert "bbox.xmin BETWEEN ? AND ?" in sql

    def test_no_limit(self):
        """Composition groups all classes, no LIMIT needed."""
        sql, _ = building_composition_query(52.37, 4.90, 1000, "buildings")
        assert "LIMIT" not in sql
