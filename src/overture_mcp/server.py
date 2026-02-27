"""
MCP Server — main entry point.

Supports two tool modes:
- direct: each operation is an MCP tool (default)
- progressive: 3 meta-tools (list_operations, get_operation_schema, execute_operation)

Both modes use the same operation registry and handlers.

Transports:
- stdio (default): for local MCP clients (Claude Desktop, Claude Code)
- sse:            for remote/hosted deployments (Railway, etc.)

Usage:
    python -m overture_mcp.server                              # stdio (default)
    TRANSPORT=sse python -m overture_mcp.server                # SSE on port 8000
    overture-mcp-server                                        # via entry point
    fastmcp run overture_mcp.server:mcp                        # via FastMCP CLI
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from overture_mcp.auth import create_auth_verifier
from overture_mcp.config import ServerConfig, load_config
from overture_mcp.db import Database
from overture_mcp.operations.buildings import BuildingsOperations
from overture_mcp.operations.divisions import DivisionsOperations
from overture_mcp.operations.land_use import LandUseOperations
from overture_mcp.operations.places import PlacesOperations
from overture_mcp.operations.transportation import TransportationOperations
from overture_mcp.registry import OperationDef, OperationRegistry
from overture_mcp.response import error_response
from overture_mcp.validation import ValidationError

logger = logging.getLogger(__name__)

# Server start time for uptime tracking in /health
_start_time: float = 0.0

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

    Resolution order:
    1. Explicit path (if provided and exists)
    2. CATEGORIES_PATH environment variable
    3. Bundled data/categories.json (shipped with the package)

    Args:
        categories_path: Optional path to categories JSON file.

    Returns:
        List of category dicts with 'category' and 'description' keys.
    """
    # 1. Explicit path argument
    if categories_path and os.path.exists(categories_path):
        with open(categories_path) as f:
            return json.load(f)

    # 2. Environment variable
    env_path = os.environ.get("CATEGORIES_PATH", "")
    if env_path and os.path.exists(env_path):
        with open(env_path) as f:
            return json.load(f)

    # 3. Bundled with the package
    bundled_path = os.path.join(os.path.dirname(__file__), "data", "categories.json")
    if os.path.exists(bundled_path):
        with open(bundled_path) as f:
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
    transportation_ops = TransportationOperations(db, config)
    land_use_ops = LandUseOperations(db, config)

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
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 500, "category": "cafe"},
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

    # Transportation theme
    registry.register(OperationDef(
        name="road_count_by_class",
        description="Count road segments by class within a radius of a point",
        theme="transportation",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point (-90 to 90)"},
                "lng": {"type": "number", "description": "Longitude of center point (-180 to 180)"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
            },
            "required": ["lat", "lng", "radius_m"],
        },
        handler=transportation_ops.road_count_by_class,
        example={
            "operation": "road_count_by_class",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        },
    ))

    registry.register(OperationDef(
        name="nearest_road_of_class",
        description="Find the single closest road segment of a given class to a point",
        theme="transportation",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point (-90 to 90)"},
                "lng": {"type": "number", "description": "Longitude of center point (-180 to 180)"},
                "road_class": {"type": "string", "description": "Road class (e.g., residential, primary, motorway)"},
                "max_radius_m": {"type": "integer", "description": "Maximum search radius in meters (1 to 50000, default: 5000)"},
                "include_geometry": {"type": "boolean", "description": "Include WKT geometry in results (default: false)"},
            },
            "required": ["lat", "lng", "road_class"],
        },
        handler=transportation_ops.nearest_road_of_class,
        example={
            "operation": "nearest_road_of_class",
            "params": {"lat": 52.3676, "lng": 4.9041, "road_class": "secondary"},
        },
    ))

    registry.register(OperationDef(
        name="road_surface_composition",
        description="Get the percentage breakdown of road surface types within a radius",
        theme="transportation",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point (-90 to 90)"},
                "lng": {"type": "number", "description": "Longitude of center point (-180 to 180)"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
            },
            "required": ["lat", "lng", "radius_m"],
        },
        handler=transportation_ops.road_surface_composition,
        example={
            "operation": "road_surface_composition",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        },
    ))

    # Land Use theme
    registry.register(OperationDef(
        name="land_use_at_point",
        description="Determine the land use designation at a specific point",
        theme="land_use",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of the point (-90 to 90)"},
                "lng": {"type": "number", "description": "Longitude of the point (-180 to 180)"},
            },
            "required": ["lat", "lng"],
        },
        handler=land_use_ops.land_use_at_point,
        example={
            "operation": "land_use_at_point",
            "params": {"lat": 52.3676, "lng": 4.9041},
        },
    ))

    registry.register(OperationDef(
        name="land_use_composition",
        description="Get the percentage breakdown of land use types within a radius",
        theme="land_use",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point (-90 to 90)"},
                "lng": {"type": "number", "description": "Longitude of center point (-180 to 180)"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
            },
            "required": ["lat", "lng", "radius_m"],
        },
        handler=land_use_ops.land_use_composition,
        example={
            "operation": "land_use_composition",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 1000},
        },
    ))

    registry.register(OperationDef(
        name="land_use_search",
        description="Find land use parcels of a specific subtype within a radius",
        theme="land_use",
        parameters={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude of center point (-90 to 90)"},
                "lng": {"type": "number", "description": "Longitude of center point (-180 to 180)"},
                "radius_m": {"type": "integer", "description": "Search radius in meters (1 to 50000)"},
                "subtype": {"type": "string", "description": "Land use subtype (e.g., residential, park, commercial)"},
                "limit": {"type": "integer", "description": "Max results to return (1 to 100, default: 20)"},
                "include_geometry": {"type": "boolean", "description": "Include WKT geometry in results (default: false)"},
            },
            "required": ["lat", "lng", "radius_m", "subtype"],
        },
        handler=land_use_ops.land_use_search,
        example={
            "operation": "land_use_search",
            "params": {"lat": 52.3676, "lng": 4.9041, "radius_m": 2000, "subtype": "park"},
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

    For HTTP-based transports (SSE, Streamable HTTP), auth is configured
    when OVERTURE_API_KEY is set. Clients authenticate via:
        Authorization: Bearer <api-key>

    A /health endpoint is registered for deployment health checks.

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
            "Install with: pip install 'fastmcp>=2.0,<4.0'"
        )

    # Initialize components
    if config is None:
        config = load_config()
    if db is None:
        db = Database(config)
        db.initialize()
        # Load STAC index for targeted S3 file resolution.
        # This replaces a full glob scan with targeted reads of 1-2 files,
        # dropping cold-start latency from ~50s to ~5s for large themes.
        db.load_stac_index()
    if categories is None:
        categories = load_categories()

    registry = build_registry(db, config, categories)

    # Auth for HTTP transports (no-op for stdio)
    auth = create_auth_verifier(config.api_key)

    # Create FastMCP app
    mcp_app = FastMCP(
        "Overture Maps MCP Server",
        version="0.1.0",
        auth=auth,
    )

    # Register /health endpoint for HTTP transports
    _register_health_endpoint(mcp_app, config)

    if config.tool_mode == "direct":
        _register_direct_tools(mcp_app, registry)
    else:
        _register_progressive_tools(mcp_app, registry)

    logger.info(
        f"MCP server configured: mode={config.tool_mode}, "
        f"operations={registry.count}, "
        f"data_version={config.data_version}"
    )

    return mcp_app


def _register_health_endpoint(mcp_app: "FastMCP", config: ServerConfig) -> None:
    """Register the /health endpoint for deployment health checks.

    Only works for HTTP-based transports (SSE, Streamable HTTP).
    Returns server status, data version, and uptime.
    """
    try:
        @mcp_app.custom_route("/health", methods=["GET"])
        async def health_check(request: Any) -> Any:
            # Import here to avoid requiring starlette when running stdio
            from starlette.responses import JSONResponse

            uptime = time.time() - _start_time if _start_time > 0 else 0
            return JSONResponse({
                "status": "healthy",
                "data_version": config.data_version,
                "uptime_seconds": round(uptime),
            })

        logger.info("/health endpoint registered")
    except (AttributeError, Exception) as e:
        # custom_route may not be available in all FastMCP versions
        # or with stdio transport — that's fine, /health is optional
        logger.debug(f"/health endpoint not registered: {e}")


def _register_direct_tools(mcp: "FastMCP", registry: OperationRegistry) -> None:
    """Register each operation as its own MCP tool (direct mode).

    In direct mode, agents see all operations with full parameter schemas
    at startup. No discovery step needed.
    """
    for op in registry:
        # Create a closure to capture the current op
        _register_single_tool(mcp, registry, op)


def _build_tool_function(
    registry: OperationRegistry,
    op: OperationDef,
) -> Any:
    """Build a typed async function for a single operation.

    FastMCP 3.x requires tool functions to have explicit parameter
    signatures (no **kwargs). We dynamically generate a function with
    the correct typed parameters from the operation's JSON schema.
    """
    op_name = op.name
    props = op.parameters.get("properties", {})
    required_params = set(op.parameters.get("required", []))

    type_map = {
        "number": "float",
        "integer": "int",
        "string": "str",
        "boolean": "bool",
    }

    # Build parameter strings: required first, then optional with defaults
    required_parts = []
    optional_parts = []
    param_names = []

    for param_name, param_schema in props.items():
        type_str = type_map.get(param_schema.get("type", "string"), "str")
        param_names.append(param_name)
        if param_name in required_params:
            required_parts.append(f"{param_name}: {type_str}")
        else:
            default = param_schema.get("default")
            default_repr = repr(default) if default is not None else "None"
            optional_parts.append(f"{param_name}: {type_str} = {default_repr}")

    all_params = ", ".join(required_parts + optional_parts)
    kwargs_build = ", ".join(f"'{p}': {p}" for p in param_names)

    func_code = f"""
async def {op_name}({all_params}) -> str:
    params = {{{kwargs_build}}}
    # Remove None values (optional params not provided)
    params = {{k: v for k, v in params.items() if v is not None}}
    result = await _execute(registry, '{op_name}', params)
    return _json_dumps(result)
"""

    namespace: dict[str, Any] = {
        "_execute": execute_operation,
        "_json_dumps": json.dumps,
        "registry": registry,
    }
    exec(func_code, namespace)  # noqa: S102
    fn = namespace[op_name]
    fn.__doc__ = op.description
    return fn


def _register_single_tool(
    mcp: "FastMCP",
    registry: OperationRegistry,
    op: OperationDef,
) -> None:
    """Register a single operation as an MCP tool."""
    fn = _build_tool_function(registry, op)
    mcp.add_tool(fn)


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

VALID_TRANSPORTS = {"stdio", "sse", "http"}


def main() -> None:
    """Start the MCP server.

    Reads configuration from environment variables and starts the FastMCP
    server. Transport is selected via the TRANSPORT environment variable:

    - stdio (default): Local MCP clients (Claude Desktop, Claude Code)
    - sse:            Remote/hosted deployments (legacy SSE transport)
    - http:           Remote/hosted deployments (Streamable HTTP, recommended)

    Environment variables:
        TRANSPORT: "stdio" (default), "sse", or "http"
        PORT: Server port for SSE/HTTP transports (default: 8000)
        HOST: Server host for SSE/HTTP transports (default: 0.0.0.0)
    """
    global _start_time
    _start_time = time.time()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    transport = os.environ.get("TRANSPORT", "stdio").lower()
    if transport not in VALID_TRANSPORTS:
        logger.error(
            f"Invalid TRANSPORT: '{transport}'. "
            f"Must be one of: {', '.join(sorted(VALID_TRANSPORTS))}"
        )
        raise SystemExit(1)

    app = _get_or_create_mcp()
    logger.info(f"Starting Overture Maps MCP Server (transport={transport})...")

    if transport == "stdio":
        app.run()
    else:
        host = os.environ.get("HOST", "0.0.0.0")
        port = int(os.environ.get("PORT", "8000"))
        app.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
