"""
Integration tests for FastMCP server in progressive tool mode.

Tests that the 3 meta-tools (list_operations, get_operation_schema,
run_operation) are properly registered and function correctly.

Requires fastmcp to be installed. Skipped if not available.
"""

import json
import pathlib

import pytest
from overture_mcp.server import HAS_FASTMCP

pytestmark = pytest.mark.skipif(
    not HAS_FASTMCP, reason="fastmcp not installed"
)


@pytest.fixture(scope="module")
def progressive_mcp_app():
    """Create a FastMCP app in progressive mode with fixture data."""
    from overture_mcp.config import ServerConfig
    from overture_mcp.db import Database
    from overture_mcp.server import create_mcp_app, load_categories

    fixtures = pathlib.Path(__file__).parent.parent / "fixtures"
    config = ServerConfig(
        api_key="test-key-12345",
        tool_mode="progressive",
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
class TestProgressiveModeRegistration:
    """Verify tools are registered correctly in progressive mode."""

    async def test_app_created(self, progressive_mcp_app):
        assert progressive_mcp_app is not None

    async def test_has_3_meta_tools(self, progressive_mcp_app):
        """Progressive mode should expose exactly 3 meta-tools."""
        tool_names = await _get_tool_names(progressive_mcp_app)
        assert "list_operations" in tool_names
        assert "get_operation_schema" in tool_names
        assert "run_operation" in tool_names

    async def test_no_individual_tools(self, progressive_mcp_app):
        """Progressive mode should not expose individual operation tools."""
        tool_names = await _get_tool_names(progressive_mcp_app)
        assert "places_in_radius" not in tool_names
        assert "building_count_in_radius" not in tool_names
        assert "road_count_by_class" not in tool_names
