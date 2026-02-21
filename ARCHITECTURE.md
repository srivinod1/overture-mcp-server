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
- At 13 operations (v1), the token overhead of direct mode is moderate (~4,000-5,000 tokens) but acceptable for most contexts.
- Progressive mode becomes valuable when the server is used alongside many other MCPs and context is tight.

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
Bearer token authentication via `Authorization: Bearer <key>` header. The server reads `OVERTURE_API_KEY` from environment variables and uses FastMCP's `StaticTokenVerifier` for validation. No user management, no OAuth, no database — just a shared secret to prevent unauthorized usage. Auth is only enforced on HTTP-based transports (SSE, Streamable HTTP). The stdio transport (local) has no auth — it inherits security from its local execution environment.

### 3.10 Concurrency Control
`asyncio.Semaphore(3)` limits concurrent DuckDB queries to 3. DuckDB supports concurrent reads (we are read-only), but memory is the bottleneck on Railway's constrained environment. This prevents OOM from multiple large S3 scans running in parallel.

When all semaphore slots are in use, new requests queue (the coroutine blocks on `async with semaphore`). No request is dropped. The 30-second query timeout applies per-query, not including queue wait time. If a query errors or times out, the semaphore is always released via `async with` (or try/finally). This guarantees no deadlocks.

### 3.11 SQL Injection Prevention
All user-provided string values (`category`, `query`) are handled via **parameterized queries** using DuckDB's `execute(sql, params)` with `?` placeholders. User strings never appear in SQL via f-string interpolation or string concatenation.

Additionally, `category` values are validated against the cached taxonomy before reaching SQL. If a category is not in the cache, the server returns an error immediately without querying S3. This provides a second layer of defense.

Numeric values (`lat`, `lng`, `radius_m`, `limit`) are type-validated (must be int or float within documented ranges) before reaching the query layer.

### 3.12 Spatial Filtering Strategy
Radius-based queries use a two-stage spatial filter:

1. **Bounding box pre-filter** (fast, approximate): Convert the radius from meters to approximate degree deltas and filter using Parquet bbox metadata. DuckDB skips irrelevant row groups entirely.
2. **Spheroid distance filter** (accurate): `ST_Distance_Spheroid(ST_FlipCoordinates(geometry), ST_FlipCoordinates(point)) < radius_m` for exact meter-based filtering.

**Coordinate order quirk**: DuckDB's `ST_Distance_Spheroid` expects coordinates in (lat, lng) order internally, but Overture geometries (and standard GIS convention) store coordinates as (lng, lat). All geometry arguments passed to `ST_Distance_Spheroid` must be wrapped in `ST_FlipCoordinates()` to swap (lng, lat) to (lat, lng). Without this, distance calculations return incorrect values.

This ensures the `distance_m` returned in results is consistent with the filter boundary — a place reported as 495m away will never appear when querying with a 500m radius and vice versa. `ST_DWithin` is NOT used because it operates in the geometry's coordinate units (degrees for lon/lat), not meters.

### 3.13 Coordinate Order
Operations accept `(lat, lng)` — latitude first, longitude second. Internally, DuckDB's `ST_Point` takes `(lng, lat)` — X before Y per GIS convention. The server handles this conversion. Callers always use `(lat, lng)`.

### 3.14 Geometry Size Cap
When `include_geometry=true`, WKT geometry strings are capped at 10,000 characters. If a geometry exceeds this (e.g., a complex country boundary polygon), it is omitted from the result with a note: `"geometry_note": "Geometry too large (>10,000 chars). Omitted to save tokens."` This prevents large polygons from the divisions theme from consuming agent context.

### 3.15 Structured Empty Results
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

### 3.16 Overture Data Version
Current: `2026-01-21.0`. Overture releases quarterly. The data version is configured as a single constant — updating to a new release is a one-line change.

---

## 4. MCP Interface

### Direct Mode (Default)

Each operation in the registry is registered as its own MCP tool with full parameter schemas. With 13 v1 operations, the agent sees 13 tools.

### Progressive Mode

3 MCP tools are registered. They never change as operations are added.

| Tool | Parameters | Returns | Latency |
|------|-----------|---------|---------|
| `list_operations` | None | Array of `{name, description, theme}` | <10ms |
| `get_operation_schema` | `operation` (string) | Full JSON schema + example | <10ms |
| `execute_operation` | `operation` (string), `params` (object) | Standard response envelope | 1-5s |

---

## 5. V1 Operations (13 Operations)

These are operations within the registry, not MCP tools. V1 covers five themes — enough to support real-world site selection, risk assessment, and area comparison workflows.

### Theme: Places (4 operations)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `get_place_categories` | Browse/search Overture category taxonomy | `query` (optional) |
| `places_in_radius` | Find all places matching category in radius | `lat, lng, radius_m, category` |
| `nearest_place_of_type` | Find single closest place of type X | `lat, lng, category` |
| `count_places_by_type_in_radius` | Count places of a category in area | `lat, lng, radius_m, category` |

**Enhanced place results (V1):** Each place result includes extended fields beyond name/category/location:
- `addresses` — structured address (freeform string, locality, postcode, region, country)
- `phone` — primary phone number (first from phones array, if available)
- `website` — primary website URL (first from websites array, if available)
- `brand` — brand name and Wikidata ID (for chain identification)
- `confidence` — Overture's data quality score (0.0 to 1.0)

**Default filtering:** Results exclude permanently closed places (`operating_status != 'permanently_closed'`). This is applied by default to all place queries. The `include_closed` parameter (default: false) can override this to include closed places for historical analysis.

**Spatial notes:**
- Place geometry is Point. Standard `ST_FlipCoordinates(geometry)` works directly.
- `confidence` is used for ordering when multiple results exist at similar distances.

### Theme: Buildings (2 operations)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `building_count_in_radius` | Count buildings in area | `lat, lng, radius_m` |
| `building_class_composition` | % breakdown of building types | `lat, lng, radius_m` |

**Spatial notes:**
- Building geometry is Polygon/MultiPolygon. Distance is calculated from the centroid: `ST_FlipCoordinates(ST_Centroid(geometry))`. `ST_FlipCoordinates` does not work directly on polygon geometries.

### Theme: Divisions (1 operation)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `point_in_admin_boundary` | What country/region/city contains this point | `lat, lng` |

**Spatial notes:**
- Uses `ST_Contains(geometry, ST_Point(lng, lat))` — point-in-polygon test. No `ST_FlipCoordinates` needed because `ST_Contains` operates in coordinate space (not spheroid distance).

### Theme: Transportation (3 operations)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `road_count_by_class` | Count road segments by class within a radius | `lat, lng, radius_m` |
| `nearest_road_of_class` | Find the single closest road segment of a given class | `lat, lng, road_class` |
| `road_surface_composition` | % breakdown of road surface types within a radius | `lat, lng, radius_m` |

**Data source:** `theme=transportation/type=segment/*` (~46GB globally). Segments are LineString geometries representing road centerlines.

**Road classes** (Overture `class` field, reliably populated globally):
`motorway`, `trunk`, `primary`, `secondary`, `tertiary`, `residential`, `service`, `footway`, `cycleway`, `path`, `track`, `unclassified`

**Road surface types** (Overture `road_surface` field):
`paved`, `unpaved`, `gravel`, `dirt`, `ground`, `asphalt`, `concrete`, `cobblestone`

Note: `road_surface` is null for many segments globally (~40-60% depending on region). Null surfaces are reported as `"unknown"` in composition results.

**Additional fields returned:**
- `road_flags` — array of boolean flags: `is_bridge`, `is_tunnel`, `is_link`, `is_under_construction`
- `names.primary` — road name (null for unnamed segments)
- `subtype` — `road`, `rail`, `water` (V1 queries filter to `subtype = 'road'` only)

**Excluded from V1** (sparse data, low value for agent reasoning):
- `speed_limits` — only ~10-15% populated globally. Too sparse to be useful as a universal tool.
- `width_rules` — very sparse coverage.
- `access_restrictions` — complex nested structure, sparse outside Europe.

**Spatial notes:**
- Road geometry is LineString. Distance is calculated from the nearest point on the line to the center: `ST_Distance_Spheroid(ST_FlipCoordinates(ST_PointOnSurface(geometry)), ST_FlipCoordinates(point))`. `ST_PointOnSurface` returns a point guaranteed to lie on the geometry (more robust than `ST_Centroid` for line geometries, which may return a point off the line for curved roads).
- Bbox pre-filter applies the same way as other themes.

### Theme: Land Use (3 operations)

| Operation | Purpose | Key Params |
|-----------|---------|------------|
| `land_use_at_point` | What is the land use designation at a specific point | `lat, lng` |
| `land_use_composition` | % breakdown of land use types within a radius | `lat, lng, radius_m` |
| `land_use_search` | Find land use parcels of a specific subtype within a radius | `lat, lng, radius_m, subtype` |

**Data source:** `theme=base/type=land_use/*`. Note: land use is under the `base` theme, not its own top-level theme. This is an Overture Maps organizational decision.

**Land use subtypes** (Overture `subtype` field, 22 values):
`residential`, `commercial`, `industrial`, `institutional`, `agriculture`, `aquaculture`, `recreation`, `park`, `forest`, `cemetery`, `religious`, `military`, `education`, `medical`, `transportation`, `airport`, `port`, `dam`, `quarry`, `landfill`, `brownfield`, `greenfield`

**Land use classes** (Overture `class` field, 95+ values):
More specific than subtypes — e.g., subtype `commercial` may have class `retail`, `office`, `hotel`. Land use queries return both `subtype` and `class` in results.

**Excluded from V1:**
- `land_cover` (`theme=base/type=land_cover`) — satellite-derived, 10 broad categories (trees, grass, crop, water, etc.). Too granular and imprecise for agent reasoning about "what's at this location." Land use (human-designated zoning) is more useful for site selection.
- `land` (`theme=base/type=land`) — natural terrain features (islands, peninsulas, etc.). Not useful for agent workflows.

**Spatial notes:**
- Land use geometry is Polygon/MultiPolygon.
- `land_use_at_point` uses `ST_Contains(geometry, ST_Point(lng, lat))` — point-in-polygon. Same as divisions, no `ST_FlipCoordinates` needed.
- `land_use_composition` and `land_use_search` use the centroid pattern: `ST_FlipCoordinates(ST_Centroid(geometry))` for distance calculation (same as buildings).
- A single point may be covered by multiple overlapping land use polygons (e.g., a park inside a residential zone). `land_use_at_point` returns all matching polygons.

### Future Operations (Post-V1)
- `place_density_analysis` — places per km² for category in area
- `competitive_overlap` — compare competitor density at multiple locations
- `building_attributes` — height, year built, class for specific building
- `total_building_area_in_radius` — sum of building footprints
- `admin_boundary_hierarchy` — full chain of boundaries
- `road_network_connectivity` — intersection density, dead-end detection
- `speed_limit_analysis` — when data coverage improves
- `zoning_change_detection` — compare land use across Overture releases

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
├── src/
│   └── overture_mcp/
│       ├── __init__.py
│       ├── __main__.py          # python -m overture_mcp entry point
│       ├── server.py            # FastMCP app, tool registrations, auth middleware
│       ├── config.py            # Constants: S3 paths, data version, defaults
│       ├── db.py                # DuckDB connection management, semaphore
│       ├── validation.py        # Parameter validation (coordinates, ranges, enums)
│       ├── bbox.py              # Bounding box computation for spatial pre-filter
│       ├── response.py          # Standard response envelope builder
│       ├── registry.py          # Operation registry: definitions, schemas, lookup
│       │
│       ├── operations/
│       │   ├── __init__.py
│       │   ├── places.py        # get_place_categories, places_in_radius, nearest_place_of_type, count_places
│       │   ├── buildings.py     # building_count_in_radius, building_class_composition
│       │   ├── divisions.py     # point_in_admin_boundary
│       │   ├── transportation.py  # road_count_by_class, nearest_road_of_class, road_surface_composition
│       │   └── land_use.py      # land_use_at_point, land_use_composition, land_use_search
│       │
│       └── queries/
│           ├── __init__.py
│           ├── places.py        # SQL query builders for places theme
│           ├── buildings.py     # SQL query builders for buildings theme
│           ├── divisions.py     # SQL query builders for divisions theme
│           ├── transportation.py  # SQL query builders for transportation theme
│           └── land_use.py      # SQL query builders for land use theme
│
├── tests/
│   ├── conftest.py              # Global fixtures (DuckDB, servers, known coords)
│   ├── fixtures/                # Deterministic parquet + category data
│   ├── unit/                    # Pure input → output (no DuckDB, no S3)
│   ├── integration/             # DuckDB + local parquet fixtures
│   ├── e2e/                     # Multi-operation agent workflows
│   ├── edge/                    # Boundary values, nulls, empty results
│   ├── security/                # Injection, tampering, auth bypass
│   ├── performance/             # Latency, concurrency, memory
│   └── compatibility/           # Direct vs progressive mode parity
│
└── docs/
    ├── TOOLS.md                 # MCP tool specs (both modes)
    ├── OPERATIONS.md            # Operation catalog (all operations, full specs)
    ├── DATA_MODEL.md            # Overture schema reference
    └── DEPLOYMENT.md            # Railway deployment guide
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
theme=places/type=place/              → Places operations
theme=buildings/type=building/        → Building operations
theme=divisions/type=division_area/   → Admin boundary operations
theme=transportation/type=segment/    → Transportation operations (~46GB)
theme=base/type=land_use/             → Land use operations
```

Note: Land use lives under the `base` theme, not a dedicated `land_use` theme. Transportation segments are large (~46GB) — the bbox pre-filter is critical for performance.

### Spatial Query Patterns

All radius-based queries use a two-stage spatial filter. The exact pattern varies by geometry type:

**Stage 1 — Bounding box pre-filter (degrees, fast):**
DuckDB uses Parquet row group statistics to skip irrelevant files entirely. The bbox deltas are computed from the radius in meters converted to approximate degrees.

**Stage 2 — Spheroid distance filter (meters, accurate):**
`ST_Distance_Spheroid` computes true Earth-surface distance in meters. The exact expression depends on geometry type.

**Pattern A — Point geometry (Places):**
```sql
ST_Distance_Spheroid(
    ST_FlipCoordinates(geometry),              -- flip (lng,lat) → (lat,lng)
    ST_FlipCoordinates(ST_Point(?, ?))         -- flip (lng,lat) → (lat,lng)
) < ?
```

**Pattern B — Polygon geometry (Buildings, Land Use):**
```sql
ST_Distance_Spheroid(
    ST_FlipCoordinates(ST_Centroid(geometry)),  -- centroid first, then flip
    ST_FlipCoordinates(ST_Point(?, ?))
) < ?
```
`ST_FlipCoordinates` does not work directly on polygon geometries — it can only flip Point types. `ST_Centroid` extracts the centroid point first.

**Pattern C — LineString geometry (Transportation):**
```sql
ST_Distance_Spheroid(
    ST_FlipCoordinates(ST_PointOnSurface(geometry)),  -- point on the line, then flip
    ST_FlipCoordinates(ST_Point(?, ?))
) < ?
```
`ST_PointOnSurface` is preferred over `ST_Centroid` for lines because it returns a point guaranteed to lie on the geometry (centroid of a curved road may be off the line).

**Pattern D — Point-in-polygon (Divisions, Land Use at Point):**
```sql
ST_Contains(geometry, ST_Point(?, ?))          -- lng, lat order (no flip needed)
```
`ST_Contains` operates in coordinate space, not spheroid distance. No `ST_FlipCoordinates` needed.

**`ST_DWithin` is NOT used** because it operates in the geometry's coordinate units (degrees for lon/lat data), not meters.

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
| `building_class_composition` | 1-3s | Aggregation query |
| `point_in_admin_boundary` | 2-5s | Division boundaries are large geometries |
| `road_count_by_class` (1km) | 2-5s | ~46GB dataset, bbox critical for perf |
| `road_count_by_class` (5km) | 3-8s | Larger scan of transportation data |
| `nearest_road_of_class` | 2-4s | Single result, but large scan source |
| `road_surface_composition` | 2-5s | Aggregation over transportation segments |
| `land_use_at_point` | 1-3s | Point-in-polygon, typically few matches |
| `land_use_composition` (1km) | 1-3s | Aggregation, smaller dataset than roads |
| `land_use_search` (1km) | 1-3s | Filtered search of land use parcels |

First query after cold start will be slower (DuckDB initializes S3 connection, loads Parquet metadata). Subsequent queries benefit from metadata caching.

**Transportation performance note:** The transportation segment dataset is ~46GB globally. The bbox pre-filter is essential — without it, queries would scan the entire dataset. Urban areas with dense road networks may return hundreds of segments within small radii. The `limit` parameter caps returned results; aggregation queries (`road_count_by_class`, `road_surface_composition`) count all matching segments regardless of limit.

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
- `place_density_analysis` — places per km² for category in area
- `competitive_overlap` — compare competitor density at multiple locations
- `building_attributes` — height, year built, class for specific building
- `total_building_area_in_radius` — sum of building footprints
- `admin_boundary_hierarchy` — full chain of admin boundaries
- `road_network_connectivity` — intersection density, dead-end detection
- `speed_limit_analysis` — when Overture speed limit data coverage improves (currently ~10-15%)
- `access_restrictions` — road access rules (currently sparse outside Europe)
- `land_cover_at_point` — satellite-derived ground cover (trees, grass, water, etc.)

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
- Zoning change detection (compare land use across releases)
- Streaming large result sets
