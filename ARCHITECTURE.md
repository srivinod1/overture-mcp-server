# Overture Maps MCP Server — Architecture

## 1. Project Vision

An open-source MCP server that exposes Overture Maps data as reusable spatial analytics tools for AI agents. This is the **data layer** — raw geospatial intelligence that API-wrapper MCPs cannot provide.

### What This Server Does
- Spatial analytics: density analysis, building composition, admin boundary lookups
- Direct data access to Overture's open geospatial dataset via DuckDB + S3
- Composable primitives that agents combine to answer complex location questions

### What This Server Does NOT Do
- Geocoding (use a geocoding MCP)
- Routing/directions (use a routing MCP)
- ETA calculations (use a routing MCP)
- Map rendering or tile serving
- Real-time location tracking

### Design Principle
> When you want to know "what's here?" or "how does this area compare?" — that's Overture MCP.
> When you want to know "how do I get there?" or "what's the address for these coordinates?" — use a geocoding/routing MCP.

---

## 2. Architecture Overview

```
Agent (any MCP-compatible client)
    │
    ▼ (MCP tool calls via SSE transport)
┌──────────────────────────────────────────┐
│   Overture Maps MCP Server               │
│   (Python + FastMCP)                     │
│                                          │
│   ┌────────────────────────────────┐     │  TOOL_MODE=direct:
│   │  MCP Interface                 │     │    each operation = 1 MCP tool
│   │  (configurable tool mode)      │     │  TOOL_MODE=progressive:
│   │                                │     │    3 meta-tools (list/schema/execute)
│   └──────────────┬─────────────────┘     │
│                  │                       │
│   ┌──────────────▼─────────────────┐     │
│   │  Operation Registry            │     │  Catalog of all operations
│   │  (name, description, schema,   │     │  New operations = new entry
│   │   handler function)            │     │  No MCP interface changes
│   └──────────────┬─────────────────┘     │
│                  │                       │
│   ┌──────────────▼─────────────────┐     │
│   │  Query Layer                   │     │  SQL generation
│   │  (DuckDB queries)              │     │  Parameter validation
│   └──────────────┬─────────────────┘     │
│                  │                       │
│   ┌──────────────▼─────────────────┐     │
│   │  DuckDB (in-process)           │     │  Spatial extension loaded
│   │  ← reads from S3 →            │     │  Anonymous access
│   └────────────────────────────────┘     │
└──────────────────────────────────────────┘
                │
                ▼ (HTTPS / S3 protocol)
┌──────────────────────────────────────────┐
│   Overture Maps on S3                    │
│   s3://overturemaps-us-west-2            │
│   release/2026-01-21.0/                  │
│   Format: GeoParquet                     │
└──────────────────────────────────────────┘
```

---

## 3. Key Decisions

### 3.1 Dual-Mode Tool Interface

The server supports two modes for exposing operations, controlled by the `TOOL_MODE` environment variable:

**Direct mode (`TOOL_MODE=direct`)** — **Default**

Each operation is registered as its own MCP tool. The agent sees all operations with full schemas at once:
```
Agent sees: places_in_radius, building_count_in_radius, point_in_admin_boundary, ...
Agent calls: places_in_radius({lat, lng, radius_m, category})
```

- One-step tool calls — the agent sees what's available and calls it directly.
- Compatible with all agent frameworks (CrewAI, LangChain, AutoGen, etc.).
- Trade-off: token overhead grows linearly with operation count.

**Progressive mode (`TOOL_MODE=progressive`)**

Operations are exposed through 3 meta-tools: `list_operations`, `get_operation_schema`, `execute_operation`. The agent discovers and fetches schemas on demand:
```
Turn 1: list_operations() → sees operation names + descriptions
Turn 1: get_operation_schema("places_in_radius") → gets full param schema
Turn 2: execute_operation("places_in_radius", {lat, lng, radius_m, category})
```

- Context overhead stays at ~300 tokens regardless of operation count.
- Follows the [code execution MCP pattern](https://www.anthropic.com/engineering/code-execution-with-mcp) recommended by Anthropic.
- Trade-off: requires multi-step discovery before first use.

**Why default to direct mode:**
- Most agent frameworks (CrewAI, LangChain, etc.) expect direct tool definitions at startup.
- At 7 operations (v1), the token overhead of direct mode is small (~2,000-3,000 tokens).
- Progressive mode becomes valuable when the operation count grows to 15+ and the server is used alongside many other MCPs.

Both modes use the same operation registry internally. Switching is a single env var change with no code or behavior differences.

### 3.2 Operation Registry (Internal Architecture)

All operations are defined in a central registry — a dictionary of operation definitions:

```python
{
    "places_in_radius": {
        "name": "places_in_radius",
        "description": "Find all places matching a category within a radius of a point",
        "parameters": { ... json schema ... },
        "handler": places_in_radius_handler,
        "theme": "places",
        "example": { ... }
    },
    ...
}
```

Both tool modes read from this registry. Adding a new operation means:
1. Write the query logic
2. Add an entry to the registry

In direct mode, the new operation automatically appears as a new MCP tool. In progressive mode, it appears in `list_operations` results. No changes to `server.py` in either case.

### 3.3 No Geocoding, No Routing
Other MCPs already handle geocoding, routing, and directions well via their APIs. We focus exclusively on spatial analytics that require direct data access — things those API wrappers cannot do.

### 3.4 Coordinates Only — No Address Inputs
All operations accept `(lat, lng)` as input. The agent is responsible for geocoding addresses via another MCP before calling Overture operations. This keeps our operations pure, fast, and dependency-free.

### 3.5 Meters for All Distances
Every radius/distance parameter uses meters. No unit conversion parameters. This matches spatial database conventions (PostGIS, DuckDB Spatial, H3).

### 3.6 Simplified JSON Responses (No Geometry by Default)
Operation responses return compact JSON optimized for agent token consumption:
- Count/density operations → numbers and summary stats
- Search operations → `{name, category, lat, lng, distance_m}`
- Optional `include_geometry=true` flag for map visualization use cases

Geometry is expensive in tokens and rarely needed for agent reasoning.

### 3.7 LLM-Native Category Discovery
Instead of a static lookup table mapping "coffee shop" → Overture category IDs, we expose `get_place_categories` as an operation that returns the real Overture taxonomy. The agent calls it, sees the actual categories, and picks the right one. This is self-updating, handles ambiguity naturally, and covers the long tail of user language.

### 3.8 Anonymous S3 Access
Overture's S3 bucket is publicly accessible. DuckDB queries it without AWS credentials:
```sql
SET s3_region='us-west-2';
-- No credentials needed
```
This eliminates AWS IAM configuration from deployment.

### 3.9 API Key Authentication
Simple `X-API-Key` header validation. The server reads `OVERTURE_API_KEY` from environment variables. No user management, no OAuth, no database — just a shared secret to prevent unauthorized usage.

### 3.10 Concurrency Control
`asyncio.Semaphore(3)` limits concurrent DuckDB queries to 3. DuckDB supports concurrent reads (we are read-only), but memory is the bottleneck on Railway's constrained environment. This prevents OOM from multiple large S3 scans running in parallel.

### 3.11 Structured Empty Results
Zero results is valid data, not an error. Response format:
```json
{
  "results": [],
  "count": 0,
  "query_params": {"lat": 52.37, "lng": 4.89, "radius_m": 500, "category": "bank"},
  "suggestion": "No banks found within 500m. Try increasing radius to 1000m."
}
```
Agents need structured data to reason and self-correct.

### 3.12 Overture Data Version
Current: `2026-01-21.0`. Overture releases quarterly. The data version is configured as a single constant — updating to a new release is a one-line change.

---

## 4. MCP Interface

### Direct Mode (Default)

Each operation in the registry is registered as its own MCP tool with full parameter schemas. With 7 v1 operations, the agent sees 7 tools.

### Progressive Mode

3 MCP tools are registered. They never change as operations are added.

| Tool | Parameters | Returns | Latency |
|------|-----------|---------|---------|
| `list_operations` | None | Array of `{name, description, theme}` | <10ms |
| `get_operation_schema` | `operation` (string) | Full JSON schema + example | <10ms |
| `execute_operation` | `operation` (string), `params` (object) | Standard response envelope | 1-5s |

---

## 5. V1 Operations (7 Operations)

These are operations within the registry, not MCP tools.

### Theme: Places (4 operations)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `get_place_categories` | Browse/search Overture category taxonomy | `query` (optional) |
| `places_in_radius` | Find all places matching category in radius | `lat, lng, radius_m, category` |
| `nearest_place_of_type` | Find single closest place of type X | `lat, lng, category` |
| `count_places_by_type_in_radius` | Count places of a category in area | `lat, lng, radius_m, category` |

### Theme: Buildings (2 operations)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `building_count_in_radius` | Count buildings in area | `lat, lng, radius_m` |
| `building_class_composition` | % breakdown of building types | `lat, lng, radius_m` |

### Theme: Divisions (1 operation)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `point_in_admin_boundary` | What country/region/city contains this point | `lat, lng` |

### Future Operations (Not in V1)
- `place_density_analysis` — places per km² for category in area
- `competitive_overlap` — compare competitor density at multiple locations
- `building_attributes` — height, year built, class for specific building
- `total_building_area_in_radius` — sum of building footprints
- `nearest_road` / `road_count_by_type` — road theme operations
- `admin_boundary_hierarchy` — full chain of boundaries

Adding any of these is a registry entry + query logic. No MCP interface changes.

---

## 6. Response Format Standard

All operations follow a consistent response envelope:

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

**Fields:**
- `results` — Array of result objects (operation-specific schema). Empty array for zero results.
- `count` — Integer count of results.
- `query_params` — Echo of the input parameters (helps agents verify what was queried).
- `data_version` — Overture release version used.
- `suggestion` — Null when results exist. Helpful hint when results are empty (e.g., "Try increasing radius to 1000m").

**Optional geometry:**
When `include_geometry=true` is passed, each result object includes a `geometry` field with WKT string.

---

## 7. Project Structure

```
overture-mcp-server/
├── README.md                    # Project overview, quick start
├── ARCHITECTURE.md              # This file — all decisions documented
├── LICENSE                      # MIT
├── pyproject.toml               # Python project config (dependencies, metadata)
├── Dockerfile                   # Railway deployment
├── railway.toml                 # Railway config
│
├── docs/
│   ├── TOOLS.md                 # MCP tool specs (3 tools)
│   ├── OPERATIONS.md            # Operation catalog (all operations, full specs)
│   ├── DATA_MODEL.md            # Overture schema reference
│   └── DEPLOYMENT.md            # Railway deployment guide
│
├── src/
│   └── overture_mcp/
│       ├── __init__.py
│       ├── server.py            # FastMCP app, 3 tool registrations, auth middleware
│       ├── config.py            # Constants: S3 paths, data version, defaults
│       ├── db.py                # DuckDB connection management, semaphore
│       ├── response.py          # Standard response envelope builder
│       ├── registry.py          # Operation registry: definitions, schemas, lookup
│       │
│       ├── operations/
│       │   ├── __init__.py
│       │   ├── places.py        # get_place_categories, places_in_radius, nearest_place_of_type, count_places
│       │   ├── buildings.py     # building_count_in_radius, building_class_composition
│       │   └── divisions.py     # point_in_admin_boundary
│       │
│       └── queries/
│           ├── __init__.py
│           ├── places.py        # SQL query builders for places theme
│           ├── buildings.py     # SQL query builders for buildings theme
│           └── divisions.py     # SQL query builders for divisions theme
│
└── tests/
    ├── conftest.py              # Shared fixtures (DuckDB test connection)
    ├── test_registry.py         # Registry lookup, schema validation
    ├── test_places.py
    ├── test_buildings.py
    └── test_divisions.py
```

**Separation of concerns:**
- `server.py` — MCP tool registration (direct or progressive mode). Thin layer that delegates to the registry.
- `registry.py` — Central catalog of all operations. Maps names → schemas + handlers.
- `operations/` — Operation handlers (parameter validation, response shaping).
- `queries/` — Pure SQL query builders. No MCP or registry knowledge. Testable independently.
- `db.py` — Single place for DuckDB connection lifecycle and concurrency control.
- `response.py` — Single place for the response envelope format.

---

## 8. Data Access Patterns

### S3 Path Template
```
s3://overturemaps-us-west-2/release/{VERSION}/theme={THEME}/type={TYPE}/
```

### Paths Used in V1
```
theme=places/type=place/          → Places operations
theme=buildings/type=building/    → Building operations
theme=divisions/type=division_area/  → Admin boundary operations
```

### Spatial Query Pattern
All radius-based queries use DuckDB Spatial's `ST_DWithin` with `ST_Point`:
```sql
SELECT *
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=places/type=place/*')
WHERE ST_DWithin(
    geometry,
    ST_Point({lng}, {lat}),
    {radius_m}
)
AND categories.primary = '{category}'
```

### Bounding Box Pre-filter
For performance, add a bounding box pre-filter before the distance check. DuckDB can use Parquet row group statistics to skip irrelevant files:
```sql
WHERE bbox.xmin BETWEEN {lng - delta} AND {lng + delta}
  AND bbox.ymin BETWEEN {lat - delta} AND {lat + delta}
  AND ST_DWithin(geometry, ST_Point({lng}, {lat}), {radius_m})
```

---

## 9. Configuration

### Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `OVERTURE_API_KEY` | Yes | API key for client authentication |
| `TOOL_MODE` | No | `direct` (default) or `progressive` — how operations are exposed as MCP tools |
| `OVERTURE_DATA_VERSION` | No | Override data version (default: `2026-01-21.0`) |
| `MAX_CONCURRENT_QUERIES` | No | Semaphore limit (default: `3`) |
| `MAX_RADIUS_M` | No | Safety cap on radius queries (default: `50000` / 50km) |
| `PORT` | No | Server port (default: `8000`) |

### Safety Limits
- Max radius: 50km (prevents full-table scans)
- Max results per query: 100 (prevents token explosion in agent responses)
- Query timeout: 30 seconds (prevents hung queries on cold S3 reads)

---

## 10. Deployment

### Target: Railway
- Runtime: Python 3.10+
- Estimated cost: $5-10/month
- No persistent storage needed (DuckDB is in-process, queries S3 directly)

### Container
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY src/ src/
CMD ["python", "-m", "overture_mcp.server"]
```

### Health Check
Expose `/health` endpoint that:
1. Confirms DuckDB can query S3 (runs a trivial count query)
2. Returns data version and server uptime

---

## 11. Performance Expectations

| Operation | Expected Latency | Notes |
|-----------|-------------------|-------|
| `list_operations` | <10ms | In-memory registry read |
| `get_operation_schema` | <10ms | In-memory registry read |
| `get_place_categories` | <100ms | Cached on server startup |
| `places_in_radius` (500m) | 1-3s | S3 cold read + spatial filter |
| `places_in_radius` (5km) | 2-5s | Larger scan area |
| `building_count_in_radius` | 1-3s | Count-only, no data transfer |
| `point_in_admin_boundary` | 2-5s | Division boundaries are large geometries |

First query after cold start will be slower (DuckDB initializes S3 connection, loads Parquet metadata). Subsequent queries benefit from metadata caching.

---

## 12. Versioning & Updates

- **Server version**: Semantic versioning (v1.0.0, v1.1.0, etc.)
- **Data version**: Tracks Overture release (2026-01-21.0). Updated quarterly.
- **Breaking changes**: New major version. Old operations never change signatures — only add new operations.
- **Data update process**: Change `OVERTURE_DATA_VERSION` env var, redeploy. No migration needed.
- **Adding operations**: Registry entry + query logic. No MCP interface changes. Non-breaking by design.

---

## 13. Future Roadmap (Post-V1)

### V2 — More Operations
- Place density analysis
- Competitive overlap
- Building attributes (height, year built)
- Total building area
- Road theme operations (nearest road, road types, restrictions)
- Admin boundary hierarchy

All added as registry entries. No MCP interface changes.

### V3 — Performance
- Parquet metadata caching
- Pre-computed spatial indexes for hot regions
- Result caching (Redis or in-memory LRU)
- Batch query support (multiple points in one call)

### V4 — Advanced
- Temporal analysis (compare across Overture releases)
- Custom area analysis (polygon input, not just radius)
- Cross-theme joins (buildings + places + roads in one query)
- Streaming large result sets
