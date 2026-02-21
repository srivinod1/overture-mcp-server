# MCP Tool Specifications

The server supports two tool modes, controlled by the `TOOL_MODE` environment variable. Both modes expose the same operations with the same behavior — only the MCP surface differs.

See [OPERATIONS.md](OPERATIONS.md) for the full catalog of operations and their parameters.

---

## Direct Mode (`TOOL_MODE=direct`) — Default

Each operation is registered as its own MCP tool. The agent sees all operations with full parameter schemas at startup.

**Exposed tools (v1):**

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_place_categories` | `query` | Search Overture's place category taxonomy |
| `places_in_radius` | `lat, lng, radius_m, category, limit, include_geometry, include_closed` | Find places matching a category within a radius |
| `nearest_place_of_type` | `lat, lng, category, max_radius_m, include_geometry, include_closed` | Find the single closest place of a given type |
| `count_places_by_type_in_radius` | `lat, lng, radius_m, category` | Count places of a category in an area |
| `building_count_in_radius` | `lat, lng, radius_m` | Count buildings in an area |
| `building_class_composition` | `lat, lng, radius_m` | Get % breakdown of building types |
| `point_in_admin_boundary` | `lat, lng` | Find what country/region/city contains a point |
| `road_count_by_class` | `lat, lng, radius_m` | Count road segments by class in an area |
| `nearest_road_of_class` | `lat, lng, road_class, max_radius_m, include_geometry` | Find the closest road of a given class |
| `road_surface_composition` | `lat, lng, radius_m` | Get % breakdown of road surface types |
| `land_use_at_point` | `lat, lng` | Find land use designation at a point |
| `land_use_composition` | `lat, lng, radius_m` | Get % breakdown of land use types in an area |
| `land_use_search` | `lat, lng, radius_m, subtype, limit, include_geometry` | Find land use parcels of a specific type |

**Agent workflow:**
```
Turn 1: places_in_radius({lat: 52.36, lng: 4.90, radius_m: 500, category: "coffee_shop"})
Turn 1: land_use_composition({lat: 52.36, lng: 4.90, radius_m: 1000})
```

One-step calls. No discovery needed. Compatible with CrewAI, LangChain, AutoGen, and other frameworks that read tool definitions at startup.

**Trade-off:** Token overhead grows with operation count. At 13 operations this is ~4,000-5,000 tokens — acceptable for most contexts. At 20+ operations it becomes significant if the server is used alongside many other MCPs.

---

## Progressive Mode (`TOOL_MODE=progressive`)

Operations are exposed through 3 meta-tools. Agents discover and fetch schemas on demand, keeping context lightweight.

**Exposed tools (always 3, regardless of operation count):**

### `list_operations`

Returns all available operation names with one-line descriptions, grouped by theme.

**Parameters:** None.

**Response:**
```json
{
  "operations": [
    {
      "name": "get_place_categories",
      "description": "Search and browse the Overture Maps place category taxonomy",
      "theme": "places"
    },
    {
      "name": "places_in_radius",
      "description": "Find all places matching a category within a radius of a point",
      "theme": "places"
    },
    {
      "name": "building_count_in_radius",
      "description": "Count buildings within a radius of a point",
      "theme": "buildings"
    }
  ]
}
```

**Notes:**
- Agents typically call this once at the start of a conversation.
- Latency: <10ms (reads from in-memory registry).

---

### `get_operation_schema`

Returns the full parameter schema and an example for a specific operation.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `operation` | string | Yes | Name of the operation (from `list_operations`) |

**Response:**
```json
{
  "name": "places_in_radius",
  "description": "Find all places matching a category within a radius of a point",
  "parameters": {
    "type": "object",
    "properties": {
      "lat": {
        "type": "number",
        "description": "Latitude of center point (-90 to 90)"
      },
      "lng": {
        "type": "number",
        "description": "Longitude of center point (-180 to 180)"
      },
      "radius_m": {
        "type": "integer",
        "description": "Search radius in meters (1 to 50000)"
      },
      "category": {
        "type": "string",
        "description": "Overture category ID (use get_place_categories to discover valid IDs)"
      },
      "limit": {
        "type": "integer",
        "description": "Max results to return (1 to 100, default: 20)"
      },
      "include_geometry": {
        "type": "boolean",
        "description": "Include WKT geometry in results (default: false)"
      }
    },
    "required": ["lat", "lng", "radius_m", "category"]
  },
  "example": {
    "operation": "places_in_radius",
    "params": {
      "lat": 52.3676,
      "lng": 4.9041,
      "radius_m": 500,
      "category": "coffee_shop"
    }
  }
}
```

**Error:**
```json
{
  "error": "Unknown operation: 'foo'. Use list_operations to see available operations."
}
```

---

### `execute_operation`

Runs an operation with the given parameters and returns results.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `operation` | string | Yes | Name of the operation to execute |
| `params` | object | Yes | Operation-specific parameters (see `get_operation_schema`) |

**Response:** Standard response envelope (see [OPERATIONS.md](OPERATIONS.md) for operation-specific responses).

```json
{
  "results": [...],
  "count": 2,
  "query_params": { ... },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

---

### Progressive Mode Agent Workflow

```
Turn 1:
  Agent → list_operations()
  Agent → get_operation_schema("places_in_radius")
  Agent → get_operation_schema("building_class_composition")

Turn 2:
  Agent → execute_operation("places_in_radius", {lat: 52.36, lng: 4.90, ...})
  Agent → execute_operation("building_class_composition", {lat: 52.36, lng: 4.90, ...})

Turn 3+:
  Agent reuses schema knowledge for additional calls — no re-fetching needed.
```

**Trade-off:** Requires multi-step discovery before first use, but context overhead stays at ~300 tokens regardless of operation count.

---

## Response Envelope (Both Modes)

All operations return the same response format regardless of tool mode:

```json
{
  "results": [...],
  "count": 3,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 500,
    "category": "coffee_shop"
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `results` | array | Operation-specific result objects. Empty array for zero results. |
| `count` | integer | Number of results returned. |
| `query_params` | object | Echo of input parameters. |
| `data_version` | string | Overture Maps release version used. |
| `suggestion` | string or null | Hint when results are empty. Null when results exist. |

## Error Responses (Both Modes)

All errors return a structured JSON object:

```json
{
  "error": "lat must be between -90 and 90. Received: 200",
  "error_type": "validation_error",
  "query_params": {
    "lat": 200,
    "lng": 4.9041,
    "radius_m": 500,
    "category": "coffee_shop"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `error` | string | Description of the error. |
| `error_type` | string | One of: `validation_error`, `query_timeout`, `internal_error`, `auth_error`. |
| `query_params` | object | Echo of input parameters (when available). |

### Common Errors

| Error | Type | Cause |
|-------|------|-------|
| `"lat must be between -90 and 90"` | `validation_error` | Invalid latitude |
| `"lng must be between -180 and 180"` | `validation_error` | Invalid longitude |
| `"radius_m must be between 1 and 50000"` | `validation_error` | Radius out of bounds |
| `"Unknown category: {x}. Use get_place_categories to find valid categories."` | `validation_error` | Invalid category ID |
| `"Query timeout after 30s. Try a smaller radius."` | `query_timeout` | S3 query took too long |
| `"Missing required parameter: {x}"` | `validation_error` | Required param not provided |
| `"Unknown operation: {x}. Use list_operations to see available operations."` | `validation_error` | Invalid operation name (progressive mode) |
