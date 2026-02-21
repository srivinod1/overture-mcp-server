# MCP Tool Specifications

The server exposes exactly **3 MCP tools**. These tools never change as operations are added or removed. They provide progressive disclosure: agents discover what's available, fetch schemas on demand, and execute operations — without loading all operation definitions into context upfront.

See [OPERATIONS.md](OPERATIONS.md) for the full catalog of operations available through `execute_operation`.

---

## Tool 1: `list_operations`

Returns all available operation names with one-line descriptions, grouped by theme.

### Parameters

None.

### Response

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
      "name": "nearest_place_of_type",
      "description": "Find the single closest place of a given type to a point",
      "theme": "places"
    },
    {
      "name": "count_places_by_type_in_radius",
      "description": "Count places of a category within a radius",
      "theme": "places"
    },
    {
      "name": "building_count_in_radius",
      "description": "Count buildings within a radius of a point",
      "theme": "buildings"
    },
    {
      "name": "building_class_composition",
      "description": "Get percentage breakdown of building types in an area",
      "theme": "buildings"
    },
    {
      "name": "point_in_admin_boundary",
      "description": "Find what country, region, and city contain a given point",
      "theme": "divisions"
    }
  ]
}
```

### Notes
- Returns the full list every time. With 7 operations this is ~500 tokens. Even at 30+ operations it stays under 2,000 tokens.
- Agents typically call this once at the start of a conversation.
- Latency: <10ms (reads from in-memory registry).

---

## Tool 2: `get_operation_schema`

Returns the full parameter schema and an example for a specific operation. Agents call this to learn how to use an operation before calling `execute_operation`.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `operation` | string | Yes | Name of the operation (from `list_operations`) |

### Response

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

### Error Response

```json
{
  "error": "Unknown operation: 'foo'. Use list_operations to see available operations."
}
```

### Notes
- Agents only fetch schemas for operations they intend to use.
- Once fetched, the agent reuses the schema knowledge for subsequent calls — no need to re-fetch.
- Latency: <10ms (reads from in-memory registry).

---

## Tool 3: `execute_operation`

Runs an operation with the given parameters and returns results.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `operation` | string | Yes | Name of the operation to execute |
| `params` | object | Yes | Operation-specific parameters (see `get_operation_schema`) |

### Response

All operations return the standard response envelope:

```json
{
  "results": [...],
  "count": 2,
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

### Error Responses

**Unknown operation:**
```json
{
  "error": "Unknown operation: 'foo'. Use list_operations to see available operations."
}
```

**Invalid parameters:**
```json
{
  "error": "radius_m must be between 1 and 50000. Received: 100000",
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 100000
  }
}
```

**Query timeout:**
```json
{
  "error": "Query timeout after 30s. Try a smaller radius.",
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 50000,
    "category": "restaurant"
  }
}
```

### Common Validation Errors

| Error | Cause |
|-------|-------|
| `"lat must be between -90 and 90"` | Invalid latitude |
| `"lng must be between -180 and 180"` | Invalid longitude |
| `"radius_m must be between 1 and 50000"` | Radius out of bounds |
| `"Unknown category: {x}. Use get_place_categories operation to find valid categories."` | Invalid category ID |
| `"Query timeout after 30s. Try a smaller radius."` | S3 query took too long |

---

## Agent Workflow Example

A site selection agent comparing two retail locations:

```
Turn 1:
  Agent → list_operations()
  Agent → get_operation_schema("places_in_radius")
  Agent → get_operation_schema("building_class_composition")

Turn 2:
  Agent → execute_operation("places_in_radius", {lat: 52.36, lng: 4.90, radius_m: 1000, category: "restaurant"})
  Agent → execute_operation("building_class_composition", {lat: 52.36, lng: 4.90, radius_m: 1000})

Turn 3:
  Agent → execute_operation("places_in_radius", {lat: 52.38, lng: 4.87, radius_m: 1000, category: "restaurant"})
  Agent → execute_operation("building_class_composition", {lat: 52.38, lng: 4.87, radius_m: 1000})

Turn 4:
  Agent compares results and recommends location A or B.
```

The agent fetched schemas once (turn 1) and reused them for all subsequent calls (turns 2-3). No schema re-fetching, no wasted tokens.
