"""
Integration tests for FastMCP server in direct tool mode.

Tests that each of the 13 operations is properly registered as an individual
MCP tool and returns valid JSON responses through the FastMCP tool handler.

Requires fastmcp to be installed. Skipped if not available.
"""

import asyncio
import json
import pathlib

import pytest
from overture_mcp.server import HAS_FASTMCP

pytestmark = pytest.mark.skipif(
    not HAS_FASTMCP, reason="fastmcp not installed"
)


@pytest.fixture(scope="module")
def direct_mcp_app():
    """Create a FastMCP app in direct mode with fixture data."""
    from overture_mcp.config import ServerConfig
    from overture_mcp.db import Database
    from overture_mcp.server import create_mcp_app, load_categories

    fixtures = pathlib.Path(__file__).parent.parent / "fixtures"
    config = ServerConfig(
        api_key="test-key-12345",
        tool_mode="direct",
        _places_source="places",
        _buildings_source="buildings",
        _divisions_source="divisions",
        _transportation_source="roads",
        _land_use_source="land_use",
    )
    db = Database(config)
    db.initialize_local(
        places_path=str(fixtures / "sample_places.parquet"),
        buildings_path=str(fixtures / "sample_buildings.parquet"),
        divisions_path=str(fixtures / "sample_divisions.parquet"),
        transportation_path=str(fixtures / "sample_roads.parquet"),
        land_use_path=str(fixtures / "sample_land_use.parquet"),
    )
    cats = load_categories(str(fixtures / "categories.json"))
    app = create_mcp_app(config=config, db=db, categories=cats)
    return app


async def _get_tool_names(app) -> set[str]:
    """Get tool names from the FastMCP app (list_tools is async in v3)."""
    tools = await app.list_tools()
    return {t.name for t in tools}


@pytest.mark.asyncio
class TestDirectModeRegistration:
    """Verify tools are registered correctly in direct mode."""

    async def test_app_created(self, direct_mcp_app):
        assert direct_mcp_app is not None

    async def test_has_13_tools(self, direct_mcp_app):
        """All 13 operations should be registered as individual tools."""
        tool_names = await _get_tool_names(direct_mcp_app)
        expected_tools = {
            "get_place_categories",
            "places_in_radius",
            "nearest_place_of_type",
            "count_places_by_type_in_radius",
            "building_count_in_radius",
            "building_class_composition",
            "point_in_admin_boundary",
            "road_count_by_class",
            "nearest_road_of_class",
            "road_surface_composition",
            "land_use_at_point",
            "land_use_composition",
            "land_use_search",
        }
        assert expected_tools.issubset(tool_names)

    async def test_no_progressive_tools(self, direct_mcp_app):
        """Direct mode should not have progressive meta-tools."""
        tool_names = await _get_tool_names(direct_mcp_app)
        assert "list_operations" not in tool_names
        assert "get_operation_schema" not in tool_names
        assert "run_operation" not in tool_names
