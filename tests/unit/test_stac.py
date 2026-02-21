"""Unit tests for STAC index module."""

import pytest
from overture_mcp.stac import StacIndex


class TestStacIndexUnloaded:
    """Tests for StacIndex when not loaded."""

    def test_not_loaded_by_default(self):
        stac = StacIndex()
        assert stac.loaded is False

    def test_resolve_returns_none_when_not_loaded(self):
        stac = StacIndex()
        result = stac.resolve("place", 52.3676, 4.9041, 500)
        assert result is None

    def test_resolve_for_point_returns_none_when_not_loaded(self):
        stac = StacIndex()
        result = stac.resolve_for_point("division_area", 52.3676, 4.9041)
        assert result is None


class TestStacIndexLoaded:
    """Tests for StacIndex with manually populated entries."""

    @pytest.fixture
    def stac_with_entries(self):
        stac = StacIndex()
        # Manually populate entries (bypassing load() which needs DuckDB)
        stac._entries = [
            {
                "collection": "place",
                "xmin": -180.0, "ymin": -90.0, "xmax": 0.0, "ymax": 45.0,
                "s3_path": "s3://bucket/places/part-00000.parquet",
            },
            {
                "collection": "place",
                "xmin": 0.0, "ymin": 30.0, "xmax": 180.0, "ymax": 90.0,
                "s3_path": "s3://bucket/places/part-00001.parquet",
            },
            {
                "collection": "place",
                "xmin": -10.0, "ymin": 40.0, "xmax": 20.0, "ymax": 60.0,
                "s3_path": "s3://bucket/places/part-00002.parquet",
            },
            {
                "collection": "building",
                "xmin": -10.0, "ymin": 40.0, "xmax": 20.0, "ymax": 60.0,
                "s3_path": "s3://bucket/buildings/part-00000.parquet",
            },
        ]
        stac._loaded = True
        return stac

    def test_loaded_is_true(self, stac_with_entries):
        assert stac_with_entries.loaded is True

    def test_resolve_finds_matching_files(self, stac_with_entries):
        # Amsterdam (52.37, 4.90) should match part-00001 and part-00002
        result = stac_with_entries.resolve("place", 52.37, 4.90, 500)
        assert result is not None
        assert "part-00001" in result
        assert "part-00002" in result
        assert "part-00000" not in result  # western hemisphere only

    def test_resolve_returns_read_parquet_format(self, stac_with_entries):
        result = stac_with_entries.resolve("place", 52.37, 4.90, 500)
        assert result.startswith("read_parquet([")
        assert result.endswith("])")

    def test_resolve_filters_by_collection(self, stac_with_entries):
        # Same location but different collection
        result = stac_with_entries.resolve("building", 52.37, 4.90, 500)
        assert result is not None
        assert "buildings" in result
        assert "places" not in result

    def test_resolve_returns_none_for_no_matches(self, stac_with_entries):
        # South pole — no files should match (all files ymin >= -90 but ymax <= 60)
        result = stac_with_entries.resolve("place", -85.0, 100.0, 500)
        assert result is None

    def test_resolve_returns_none_for_unknown_collection(self, stac_with_entries):
        result = stac_with_entries.resolve("nonexistent", 52.37, 4.90, 500)
        assert result is None

    def test_resolve_large_radius(self, stac_with_entries):
        # Large radius should match more files
        result = stac_with_entries.resolve("place", 52.37, 4.90, 50000)
        assert result is not None
        # Should still match at least part-00001 and part-00002
        assert "part-00001" in result

    def test_resolve_for_point(self, stac_with_entries):
        # Amsterdam point should be contained in part-00001 and part-00002
        result = stac_with_entries.resolve_for_point("place", 52.37, 4.90)
        assert result is not None
        assert "part-00001" in result
        assert "part-00002" in result

    def test_resolve_for_point_no_match(self, stac_with_entries):
        # Point outside all files (south of -90 ymax and east of 180)
        result = stac_with_entries.resolve_for_point("place", -85.0, 100.0)
        assert result is None

    def test_resolve_for_point_exact_boundary(self, stac_with_entries):
        # Point exactly on a file boundary edge
        result = stac_with_entries.resolve_for_point("place", 45.0, 0.0)
        assert result is not None  # Should match files that contain this edge


class TestDatabaseResolveSource:
    """Test Database.resolve_source and resolve_source_point."""

    def test_resolve_source_without_stac(self):
        """Without STAC loaded, should return fallback."""
        from overture_mcp.config import ServerConfig
        from overture_mcp.db import Database

        config = ServerConfig(api_key="test")
        db = Database(config)
        db.initialize_local()

        fallback = "some_table"
        result = db.resolve_source("place", 52.37, 4.90, 500, fallback)
        assert result == fallback

    def test_resolve_source_point_without_stac(self):
        """Without STAC loaded, should return fallback."""
        from overture_mcp.config import ServerConfig
        from overture_mcp.db import Database

        config = ServerConfig(api_key="test")
        db = Database(config)
        db.initialize_local()

        fallback = "some_table"
        result = db.resolve_source_point("division_area", 52.37, 4.90, fallback)
        assert result == fallback
