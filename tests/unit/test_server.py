"""
Unit tests for server module — factory functions and entry point logic.

Tests the MCP app creation, tool mode selection, and registry integration.
FastMCP-specific tests are skipped if fastmcp is not installed.
"""

import json

import pytest
from overture_mcp.server import (
    build_registry,
    execute_operation,
    load_categories,
    HAS_FASTMCP,
)


class TestLoadCategories:
    """Tests for category taxonomy loading."""

    def test_loads_default_categories(self):
        """Should load categories from fixture file."""
        cats = load_categories()
        assert len(cats) > 0
        assert all("category" in c for c in cats)

    def test_loads_from_custom_path(self, tmp_path):
        """Should load from a custom path if provided."""
        custom = tmp_path / "custom_cats.json"
        custom.write_text(json.dumps([
            {"category": "test_cat", "description": "A test category"},
        ]))
        cats = load_categories(str(custom))
        assert len(cats) == 1
        assert cats[0]["category"] == "test_cat"

    def test_nonexistent_path_falls_back(self):
        """Non-existent custom path should fall back to default."""
        cats = load_categories("/nonexistent/path/categories.json")
        # Falls back to fixture file
        assert len(cats) > 0

    def test_returns_list_of_dicts(self):
        cats = load_categories()
        assert isinstance(cats, list)
        for c in cats:
            assert isinstance(c, dict)
            assert "category" in c


class TestBuildRegistry:
    """Tests for registry construction."""

    def test_registers_all_operations(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        assert registry.count == 13

    def test_has_places_operations(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        assert "get_place_categories" in registry
        assert "places_in_radius" in registry
        assert "nearest_place_of_type" in registry
        assert "count_places_by_type_in_radius" in registry

    def test_has_buildings_operations(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        assert "building_count_in_radius" in registry
        assert "building_class_composition" in registry

    def test_has_divisions_operations(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        assert "point_in_admin_boundary" in registry

    def test_has_transportation_operations(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        assert "road_count_by_class" in registry
        assert "nearest_road_of_class" in registry
        assert "road_surface_composition" in registry

    def test_has_land_use_operations(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        assert "land_use_at_point" in registry
        assert "land_use_composition" in registry
        assert "land_use_search" in registry

    def test_all_operations_have_handlers(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        for op in registry:
            assert callable(op.handler), f"{op.name} has no callable handler"

    def test_all_operations_have_examples(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        for op in registry:
            assert op.example is not None, f"{op.name} has no example"

    def test_operations_grouped_by_theme(self, test_db, test_config, category_taxonomy):
        registry = build_registry(test_db, test_config, category_taxonomy)
        ops = registry.list_operations()
        themes = {o["theme"] for o in ops}
        assert themes == {"places", "buildings", "divisions", "transportation", "land_use"}


class TestExecuteOperation:
    """Tests for the operation executor."""

    @pytest.mark.asyncio
    async def test_unknown_operation(self, test_registry):
        result = await execute_operation(test_registry, "nonexistent_op", {})
        assert "error" in result
        assert result["error_type"] == "validation_error"
        assert "Unknown operation" in result["error"]

    @pytest.mark.asyncio
    async def test_validation_error_caught(self, test_registry):
        """ValidationError should be caught and returned as structured error."""
        result = await execute_operation(test_registry, "places_in_radius", {
            "lat": 999,  # invalid
            "lng": 4.9041, "radius_m": 500, "category": "cafe",
        })
        assert "error" in result
        assert result["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_successful_operation(self, test_registry):
        result = await execute_operation(test_registry, "get_place_categories", {
            "query": "coffee",
        })
        assert "error" not in result
        assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_query_params_echoed_on_error(self, test_registry):
        """Error responses should echo query_params."""
        params = {"lat": 999, "lng": 4.9041, "radius_m": 500, "category": "cafe"}
        result = await execute_operation(test_registry, "places_in_radius", params)
        assert result.get("query_params") == params


class TestCreateMcpApp:
    """Tests for MCP app factory (requires fastmcp)."""

    @pytest.mark.skipif(not HAS_FASTMCP, reason="fastmcp not installed")
    def test_create_app(self, test_db, test_config, category_taxonomy):
        from overture_mcp.server import create_mcp_app
        app = create_mcp_app(
            config=test_config, db=test_db, categories=category_taxonomy,
        )
        assert app is not None

    def test_missing_fastmcp_raises(self):
        """If fastmcp is not installed, create_mcp_app should raise ImportError."""
        if HAS_FASTMCP:
            pytest.skip("fastmcp is installed — can't test missing case")
        from overture_mcp.server import create_mcp_app
        with pytest.raises(ImportError, match="fastmcp is required"):
            create_mcp_app()
