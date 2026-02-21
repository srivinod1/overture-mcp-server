# Overture Maps MCP Server — Architecture

## 1. Project Vision

An open-source MCP server that exposes Overture Maps data as reusable spatial analytics tools for AI agents. This is the **data layer** — raw geospatial intelligence that API-wrapper MCPs (TomTom, Mapbox, Google) cannot provide.

### What This Server Does
- Spatial analytics: density analysis, building composition, admin boundary lookups
- Direct data access to Overture's open geospatial dataset via DuckDB + S3
- Composable primitives that agents combine to answer complex location questions

### What This Server Does NOT Do
- Geocoding (use TomTom/Mapbox MCP)
- Routing/directions (use TomTom/Mapbox MCP)
- ETA calculations (use TomTom/Mapbox MCP)
- Map rendering or tile serving
- Real-time location tracking

### Design Principle
> When you want to know "what's here?" or "how does this area compare?" — that's Overture MCP.
> When you want to know "how do I get there?" or "what's the address for these coordinates?" — that's TomTom/Mapbox MCP.

---

## 2. Architecture Overview

```
Claude Agent (or any MCP-compatible agent)
    │
    ▼ (MCP tool calls via SSE transport)
┌─────────────────────────────────┐
│   Overture Maps MCP Server      │
│   (Python + FastMCP)            │
│                                 │
│   ┌───────────────────────┐     │
│   │  Tool Layer           │     │  7 tools (v1)
│   │  (tool definitions)   │     │
│   └──────────┬────────────┘     │
│              │                  │
│   ┌──────────▼────────────┐     │
│   │  Query Layer          │     │  SQL generation + parameter validation
│   │  (DuckDB queries)     │     │
│   └──────────┬────────────┘     │
│              │                  │
│   ┌──────────▼────────────┐     │
│   │  DuckDB (in-process)  │     │  Spatial extension loaded
│   │  ← reads from S3 →   │     │  Anonymous access, no credentials
│   └───────────────────────┘     │
└─────────────────────────────────┘
                │
                ▼ (HTTPS / S3 protocol)
┌─────────────────────────────────┐
│   Overture Maps on S3           │
│   s3://overturemaps-us-west-2   │
│   release/2026-01-21.0/         │
│   Format: GeoParquet            │
└─────────────────────────────────┘
```

---

## 3. Key Decisions

### 3.1 No Geocoding, No Routing
Other MCPs (TomTom, Mapbox) already handle geocoding, routing, and directions well via their APIs. We focus exclusively on spatial analytics that require direct data access — things those API wrappers cannot do.

### 3.2 Coordinates Only — No Address Inputs
All tools accept `(lat, lng)` as input. The agent is responsible for geocoding addresses via another MCP before calling Overture tools. This keeps our tools pure, fast, and dependency-free.

### 3.3 Meters for All Distances
Every radius/distance parameter uses meters. No unit conversion parameters. This matches spatial database conventions (PostGIS, DuckDB Spatial, H3).

### 3.4 Simplified JSON Responses (No Geometry by Default)
Tool responses return compact JSON optimized for agent token consumption:
- Count/density tools → numbers and summary stats
- Search tools → `{name, category, lat, lng, distance_m}`
- Optional `include_geometry=true` flag for map visualization use cases

Geometry is expensive in tokens and rarely needed for agent reasoning.

### 3.5 LLM-Native Category Discovery
Instead of a static lookup table mapping "coffee shop" → Overture category IDs, we expose a `get_place_categories` tool that returns the real Overture taxonomy. The agent calls it, sees the actual categories, and picks the right one. This is self-updating, handles ambiguity naturally, and covers the long tail of user language.

### 3.6 Anonymous S3 Access
Overture's S3 bucket is publicly accessible. DuckDB queries it without AWS credentials:
```sql
SET s3_region='us-west-2';
-- No credentials needed
```
This eliminates AWS IAM configuration from deployment.

### 3.7 API Key Authentication
Simple `X-API-Key` header validation. The server reads `OVERTURE_API_KEY` from environment variables. No user management, no OAuth, no database — just a shared secret to prevent unauthorized usage.

### 3.8 Concurrency Control
`asyncio.Semaphore(3)` limits concurrent DuckDB queries to 3. DuckDB supports concurrent reads (we are read-only), but memory is the bottleneck on Railway's constrained environment. This prevents OOM from multiple large S3 scans running in parallel.

### 3.9 Structured Empty Results
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

### 3.10 Overture Data Version
Current: `2026-01-21.0`. Overture releases quarterly. The data version is configured as a single constant — updating to a new release is a one-line change.

---

## 4. V1 Tool Set (7 Tools)

### Theme: Places (4 tools)

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| `get_place_categories` | Browse/search Overture category taxonomy | `query` (optional text filter) | List of matching category IDs and labels |
| `places_in_radius` | Find all places matching filters in radius | `lat, lng, radius_m, category` | List of `{name, category, lat, lng, distance_m}` |
| `nearest_place_of_type` | Find single closest place of type X | `lat, lng, category, max_radius_m` | Single `{name, category, lat, lng, distance_m}` |
| `count_places_by_type_in_radius` | Count places of a category in area | `lat, lng, radius_m, category` | `{count, radius_m, category}` |

### Theme: Buildings (2 tools)

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| `building_count_in_radius` | Count buildings in area | `lat, lng, radius_m` | `{count, radius_m}` |
| `building_class_composition` | % breakdown of building types | `lat, lng, radius_m` | `{residential: 65%, commercial: 25%, industrial: 10%}` |

### Theme: Divisions (1 tool)

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| `point_in_admin_boundary` | What country/region/city contains this point | `lat, lng` | `{locality, region, country}` |

### V2 Candidates (Not in V1)
- `place_density_analysis` — places per km² for category in area
- `competitive_overlap` — compare competitor density at multiple locations
- `building_attributes` — height, year built, class for specific building
- `total_building_area_in_radius` — sum of building footprints
- `nearest_road` / `road_count_by_type` — road theme tools
- `admin_boundary_hierarchy` — full chain of boundaries

---

## 5. Response Format Standard

All tools follow a consistent response envelope:

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
- `results` — Array of result objects (tool-specific schema). Empty array for zero results.
- `count` — Integer count of results.
- `query_params` — Echo of the input parameters (helps agents verify what was queried).
- `data_version` — Overture release version used.
- `suggestion` — Null when results exist. Helpful hint when results are empty (e.g., "Try increasing radius to 1000m").

**Optional geometry:**
When `include_geometry=true` is passed, each result object includes a `geometry` field with WKT string.

---

## 6. Project Structure

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
│   ├── TOOLS.md                 # Detailed tool specifications
│   ├── DATA_MODEL.md            # Overture schema reference
│   └── DEPLOYMENT.md            # Railway deployment guide
│
├── src/
│   └── overture_mcp/
│       ├── __init__.py
│       ├── server.py            # FastMCP app, tool registration, auth middleware
│       ├── config.py            # Constants: S3 paths, data version, defaults
│       ├── db.py                # DuckDB connection management, semaphore
│       ├── response.py          # Standard response envelope builder
│       │
│       ├── tools/
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
    ├── test_places.py
    ├── test_buildings.py
    └── test_divisions.py
```

**Separation of concerns:**
- `tools/` — Tool definitions (parameters, descriptions, response shaping). These are the MCP interface.
- `queries/` — Pure SQL query builders. No MCP knowledge. Testable independently.
- `db.py` — Single place for DuckDB connection lifecycle and concurrency control.
- `response.py` — Single place for the response envelope format.

---

## 7. Data Access Patterns

### S3 Path Template
```
s3://overturemaps-us-west-2/release/{VERSION}/theme={THEME}/type={TYPE}/
```

### Paths Used in V1
```
theme=places/type=place/          → Places tools
theme=buildings/type=building/    → Building tools
theme=divisions/type=division_area/  → Admin boundary tools
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

## 8. Configuration

### Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `OVERTURE_API_KEY` | Yes | API key for client authentication |
| `OVERTURE_DATA_VERSION` | No | Override data version (default: `2026-01-21.0`) |
| `MAX_CONCURRENT_QUERIES` | No | Semaphore limit (default: `3`) |
| `MAX_RADIUS_M` | No | Safety cap on radius queries (default: `50000` / 50km) |
| `PORT` | No | Server port (default: `8000`) |

### Safety Limits
- Max radius: 50km (prevents full-table scans)
- Max results per query: 100 (prevents token explosion in agent responses)
- Query timeout: 30 seconds (prevents hung queries on cold S3 reads)

---

## 9. Deployment

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

## 10. Performance Expectations

| Query Type | Expected Latency | Notes |
|------------|-------------------|-------|
| `get_place_categories` | <100ms | Cached on server startup |
| `places_in_radius` (500m) | 1-3s | S3 cold read + spatial filter |
| `places_in_radius` (5km) | 2-5s | Larger scan area |
| `building_count_in_radius` | 1-3s | Count-only, no data transfer |
| `point_in_admin_boundary` | 2-5s | Division boundaries are large geometries |

First query after cold start will be slower (DuckDB initializes S3 connection, loads Parquet metadata). Subsequent queries benefit from metadata caching.

---

## 11. Versioning & Updates

- **Server version**: Semantic versioning (v1.0.0, v1.1.0, etc.)
- **Data version**: Tracks Overture release (2026-01-21.0). Updated quarterly.
- **Breaking changes**: New major version. Old tools never change signatures — only add new tools.
- **Data update process**: Change `OVERTURE_DATA_VERSION` env var, redeploy. No migration needed.

---

## 12. Future Roadmap (Post-V1)

### V2 — More Tools
- Place density analysis
- Competitive overlap
- Building attributes (height, year built)
- Total building area
- Road theme tools (nearest road, road types, restrictions)
- Admin boundary hierarchy

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
