"""
MCP Server — main entry point.

Supports two tool modes:
- direct: each operation is an MCP tool (default)
- progressive: 3 meta-tools (list_operations, get_operation_schema, execute_operation)

Both modes use the same operation registry and handlers.

Usage:
    python -m overture_mcp.server          # stdio transport (default)
    fastmcp run overture_mcp.server:mcp    # via FastMCP CLI
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from overture_mcp.config import ServerConfig, load_config
from overture_mcp.db import Database
from overture_mcp.operations.buildings import BuildingsOperations
from overture_mcp.operations.divisions import DivisionsOperations
from overture_mcp.operations.places import PlacesOperations
from overture_mcp.registry import OperationDef, OperationRegistry
from overture_mcp.response import error_response
from overture_mcp.validation import ValidationError

logger = logging.getLogger(__name__)

# FastMCP is optional — only needed when running as MCP server.
# Allows the module to be imported for testing without fastmcp installed.
try:
    from fastmcp import FastMCP
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False


# ---------------------------------------------------------------------------
# Category loading
# ---------------------------------------------------------------------------

def load_categories(categories_path: str | None = None) -> list[dict]:
    """Load the category taxonomy.

    In production, this could load from Overture data or a bundled file.
    For now, we use the fixture categories.json.

    Args:
        categories_path: Optional path to categories JSON file.

    Returns:
        List of category dicts with 'category' and 'description' keys.
    """
    if categories_path and os.path.exists(categories_path):
        with open(categories_path) as f:
            return json.load(f)

    # Default: bundled categories
    default_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "tests", "fixtures", "categories.json"
    )
    if os.path.exists(default_path):
        with open(default_path) as f:
            return json.load(f)

    logger.warning("No categories file found. Using empty taxonomy.")
    return []


# ---------------------------------------------------------------------------
# Registry setup
# ---------------------------------------------------------------------------

def build_registry(
    db: Database,
    config: ServerConfig,
    categories: list[dict],
) -> OperationRegistry:
    """Build and populate the operation registry with all v1 operations.

    Args:
        db: Database instance.
        config: Server configuration.
        categories: Category taxonomy.

    Returns:
        Populated OperationRegistry.
    """
    places_ops = PlacesOperations(db, config, categories)
    buildings_ops = BuildingsOperations(db, config)
    divisions_ops = DivisionsOperations(db, config)

    registry = OperationRegistry()

    # Places theme
    registry.register(OperationDef(
        name="get_place_categories",
        description="Search and browse the Overture Maps place category taxonomy",
        theme="places",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in category names. "
                                   "Case-insensitive substring match. "
                                   "If omitted, returns top-level categories.",
                },
            },
            "required": [],
        },
        handler=places_ops.get_place_categories,
        example={
            "operation": "get_place_categories",
            "params": {"query": "coffee"},
        },
    ))

    registry.register(OperationDef(
        name="places_in_radius",
        description="Find all places matching a category within a radius of a point",
        theme="places",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point (-90 to 90)"},
                "lng": {"type": "number", "description": "Longitude of center point (-180 to 180)"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
                "category": {"type": "string", "description": "Overture category ID (use get_place_categories to discover valid IDs)"},
                "limit": {"type": "integer", "description": "Max results to return (1 to 100, default: 20)"},
                "include_geometry": {"type": "boolean", "description": "Include WKT geometry in results (default: false)"},
            },
            "required": ["lat", "lng", "radius_m", "category"],
        },
        handler=places_ops.places_in_radius,
        example={
            "operation": "places_in_radius",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "coffee_shop"},
        },
    ))

    registry.register(OperationDef(
        name="nearest_place_of_type",
        description="Find the single closest place of a given type to a point",
        theme="places",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point"},
                "lng": {"type": "number", "description": "Longitude of center point"},
                "category": {"type": "string", "description": "Overture category ID"},
                "max_radius_m": {"type": "integer", "description": "Maximum search radius in meters (1 to 50000, default: 5000)"},
                "include_geometry": {"type": "boolean", "description": "Include WKT geometry in results (default: false)"},
            },
            "required": ["lat", "lng", "category"],
        },
        handler=places_ops.nearest_place_of_type,
        example={
            "operation": "nearest_place_of_type",
            "params": {"lat": 52.3676, "lng": 4.9041, "category": "atm"},
        },
    ))

    registry.register(OperationDef(
        name="count_places_by_type_in_radius",
        description="Count how many places of a category exist within a radius",
        theme="places",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point"},
                "lng": {"type": "number", "description": "Longitude of center point"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
                "category": {"type": "string", "description": "Overture category ID"},
            },
            "required": ["lat", "lng", "radius_m", "category"],
        },
        handler=places_ops.count_places_by_type_in_radius,
        example={
            "operation": "count_places_by_type_in_radius",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000, "category": "restaurant"},
        },
    ))

    # Buildings theme
    registry.register(OperationDef(
        name="building_count_in_radius",
        description="Count total buildings within a radius of a point",
        theme="buildings",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point"},
                "lng": {"type": "number", "description": "Longitude of center point"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
            },
            "required": ["lat", "lng", "radius_m"],
        },
        handler=buildings_ops.building_count_in_radius,
        example={
            "operation": "building_count_in_radius",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        },
    ))

    registry.register(OperationDef(
        name="building_class_composition",
        description="Get the percentage breakdown of building types within a radius",
        theme="buildings",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point"},
                "lng": {"type": "number", "description": "Longitude of center point"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
            },
            "required": ["lat", "lng", "radius_m"],
        },
        handler=buildings_ops.building_class_composition,
        example={
            "operation": "building_class_composition",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        },
    ))

    # Divisions theme
    registry.register(OperationDef(
        name="point_in_admin_boundary",
        description="Determine what administrative boundaries contain a given point",
        theme="divisions",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of the point"},
                "lng": {"type": "number", "description": "Longitude of the point"},
            },
            "required": ["lat", "lng"],
        },
        handler=divisions_ops.point_in_admin_boundary,
        example={
            "operation": "point_in_admin_boundary",
            "params": {"lat": 52.3676, "lng": 4.9041},
        },
    ))

    return registry


# ---------------------------------------------------------------------------
# Operation executor (shared by both modes)
# ---------------------------------------------------------------------------

async def execute_operation(
    registry: OperationRegistry,
    operation_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Execute a named operation with the given parameters.

    Handles validation errors and timeouts, returning structured error responses.

    Args:
        registry: The operation registry.
        operation_name: Name of the operation to execute.
        params: Operation-specific parameters.

    Returns:
        Success or error response dict.
    """
    op = registry.get(operation_name)
    if op is None:
        return error_response(
            error=f"Unknown operation: '{operation_name}'. "
                  "Use list_operations to see available operations.",
            error_type="validation_error",
        )

    try:
        return await op.handler(params)
    except ValidationError as e:
        return error_response(
            error=e.message,
            error_type="validation_error",
            query_params=params,
        )
    except asyncio.TimeoutError:
        return error_response(
            error="Query timeout after 30s. Try a smaller radius.",
            error_type="query_timeout",
            query_params=params,
        )
    except Exception as e:
        logger.exception(f"Unexpected error in operation '{operation_name}'")
        return error_response(
            error=f"Internal error: {type(e).__name__}: {e}",
            error_type="internal_error",
            query_params=params,
        )


# ---------------------------------------------------------------------------
# FastMCP application factory
# ---------------------------------------------------------------------------

def create_mcp_app(
    config: ServerConfig | None = None,
    db: Database | None = None,
    categories: list[dict] | None = None,
) -> "FastMCP":
    """Create and configure the FastMCP application.

    Initializes the database, loads categories, builds the operation registry,
    and registers MCP tools according to the configured tool mode.

    Args:
        config: Server configuration. If None, loads from environment.
        db: Database instance. If None, creates and initializes one.
        categories: Category taxonomy. If None, loads from default path.

    Returns:
        Configured FastMCP application ready to run.

    Raises:
        ImportError: If fastmcp is not installed.
    """
    if not HAS_FASTMCP:
        raise ImportError(
            "fastmcp is required to run the MCP server. "
            "Install with: pip install fastmcp"
        )

    # Initialize components
    if config is None:
        config = load_config()
    if db is None:
        db = Database(config)
        db.initialize()
    if categories is None:
        categories = load_categories()

    registry = build_registry(db, config, categories)

    # Create FastMCP app
    mcp = FastMCP(
        "Overture Maps MCP Server",
        version="0.1.0",
    )

    if config.tool_mode == "direct":
        _register_direct_tools(mcp, registry)
    else:
        _register_progressive_tools(mcp, registry)

    logger.info(
        f"MCP server configured: mode={config.tool_mode}, "
        f"operations={registry.count}, "
        f"data_version={config.data_version}"
    )

    return mcp


def _register_direct_tools(mcp: "FastMCP", registry: OperationRegistry) -> None:
    """Register each operation as its own MCP tool (direct mode).

    In direct mode, agents see all operations with full parameter schemas
    at startup. No discovery step needed.
    """
    for op in registry:
        # Create a closure to capture the current op
        _register_single_tool(mcp, registry, op)


def _register_single_tool(
    mcp: "FastMCP",
    registry: OperationRegistry,
    op: OperationDef,
) -> None:
    """Register a single operation as an MCP tool.

    Uses a factory function to create the async handler with proper
    closure over the operation name and registry.
    """
    op_name = op.name

    async def tool_handler(**kwargs: Any) -> str:
        result = await execute_operation(registry, op_name, kwargs)
        return json.dumps(result)

    # Set function metadata for FastMCP schema generation
    tool_handler.__name__ = op_name
    tool_handler.__doc__ = op.description

    # Build parameter annotations from JSON schema for FastMCP
    annotations: dict[str, Any] = {}
    props = op.parameters.get("properties", {})
    required = set(op.parameters.get("required", []))

    type_map = {
        "number": float,
        "integer": int,
        "string": str,
        "boolean": bool,
    }

    for param_name, param_schema in props.items():
        param_type = type_map.get(param_schema.get("type", "string"), str)
        if param_name not in required:
            # Optional parameters: use None as default
            annotations[param_name] = param_type
        else:
            annotations[param_name] = param_type

    tool_handler.__annotations__ = annotations
    tool_handler.__annotations__["return"] = str

    mcp.add_tool(tool_handler, name=op_name, description=op.description)


def _register_progressive_tools(
    mcp: "FastMCP", registry: OperationRegistry,
) -> None:
    """Register the 3 meta-tools for progressive discovery mode.

    In progressive mode, agents discover operations on demand:
    1. list_operations() — browse available operations
    2. get_operation_schema(operation) — get parameter details
    3. execute_operation(operation, params) — run an operation
    """

    @mcp.tool
    async def list_operations() -> str:
        """List all available spatial analytics operations grouped by theme."""
        return json.dumps({"operations": registry.list_operations()})

    @mcp.tool
    async def get_operation_schema(operation: str) -> str:
        """Get the full parameter schema and example for a specific operation.

        Args:
            operation: Name of the operation (from list_operations).
        """
        schema = registry.get_schema(operation)
        if schema is None:
            return json.dumps(error_response(
                error=f"Unknown operation: '{operation}'. "
                      "Use list_operations to see available operations.",
                error_type="validation_error",
            ))
        return json.dumps(schema)

    @mcp.tool
    async def run_operation(operation: str, params: str) -> str:
        """Execute a spatial analytics operation.

        Args:
            operation: Name of the operation to execute.
            params: JSON string of operation-specific parameters.
        """
        try:
            parsed_params = json.loads(params)
        except (json.JSONDecodeError, TypeError):
            return json.dumps(error_response(
                error="params must be a valid JSON object.",
                error_type="validation_error",
            ))

        result = await execute_operation(registry, operation, parsed_params)
        return json.dumps(result)


# ---------------------------------------------------------------------------
# Module-level MCP app (for FastMCP CLI: fastmcp run overture_mcp.server:mcp)
# ---------------------------------------------------------------------------

# Lazily created when accessed via CLI
mcp: FastMCP | None = None


def _get_or_create_mcp() -> "FastMCP":
    """Get or lazily create the module-level MCP app."""
    global mcp
    if mcp is None:
        mcp = create_mcp_app()
    return mcp


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the MCP server.

    Reads configuration from environment variables and starts the FastMCP
    server with stdio transport (default for MCP).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = _get_or_create_mcp()
    logger.info("Starting Overture Maps MCP Server...")
    app.run()


if __name__ == "__main__":
    main()
