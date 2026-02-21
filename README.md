# Overture Maps MCP Server

An open-source MCP server that exposes [Overture Maps](https://overturemaps.org/) data as spatial analytics tools for AI agents.

## What This Does

AI agents need geospatial intelligence. This server gives them direct access to Overture Maps data through clean, composable tool primitives.

**Ask questions like:**
- "How many coffee shops are within 500m of this location?"
- "What's the building composition (residential vs commercial) in this area?"
- "What city/country does this coordinate fall in?"
- "What road types are most common near this location?"
- "What is the land use around this point?"

## How It Fits in the Agent Stack

```
+---------------------------------------------------+
|  AI Agent (Claude, etc.)                          |
+-----------------+---------------------------------+
|  Geocoding /    |  Overture Maps MCP              |
|  Routing MCP    |  ----------------------         |
|  -------------- |  Place analytics                |
|  Geocoding      |  Building composition           |
|  Routing        |  Admin boundary lookups         |
|  Directions     |  Transportation analysis        |
|  ETA            |  Land use classification        |
|                 |  Category discovery             |
+-----------------+---------------------------------+
```

**Overture MCP** handles spatial analytics that need direct data access.
**Geocoding/Routing MCPs** handle geocoding, routing, and directions via APIs.

They're complementary — use them together for a complete geospatial agent.

## Available Tools (V1)

| Tool | Theme | What It Does |
|------|-------|-------------|
| `get_place_categories` | Places | Search Overture's place category taxonomy |
| `places_in_radius` | Places | Find all places matching a category within a radius |
| `nearest_place_of_type` | Places | Find the single closest place of a given type |
| `count_places_by_type_in_radius` | Places | Count places of a category in an area |
| `building_count_in_radius` | Buildings | Count buildings in an area |
| `building_class_composition` | Buildings | Get % breakdown of building types |
| `point_in_admin_boundary` | Divisions | Find what country/region/city contains a point |
| `road_count_by_class` | Transportation | Count road segments by class in an area |
| `nearest_road_of_class` | Transportation | Find the closest road of a given class |
| `road_surface_composition` | Transportation | Get % breakdown of road surface types |
| `land_use_at_point` | Land Use | Determine land use designation at a point |
| `land_use_composition` | Land Use | Get % breakdown of land use types in an area |
| `land_use_search` | Land Use | Find land use parcels of a specific subtype |

The server also supports a [progressive disclosure mode](https://www.anthropic.com/engineering/code-execution-with-mcp) (`TOOL_MODE=progressive`) that exposes 3 meta-tools instead of 13 individual tools — useful when running alongside many other MCPs where context overhead matters. See [docs/TOOLS.md](docs/TOOLS.md) for details.

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for full parameter and response specifications.

## Quick Start

### Prerequisites
- Python 3.10+
- An MCP-compatible AI agent (Claude Desktop, Claude Code, etc.)

### Install from Source

```bash
git clone https://github.com/your-username/overture-mcp-server.git
cd overture-mcp-server
pip install -e .
```

### Run Locally (stdio transport)

```bash
# stdio is default — no API key needed for local use
python -m overture_mcp.server

# or via the CLI entry point
overture-mcp-server
```

### Run as Hosted Server (SSE transport)

```bash
export OVERTURE_API_KEY="your-api-key"
export TRANSPORT=sse
python -m overture_mcp.server
# Server starts on http://0.0.0.0:8000
```

### Connect from Claude Desktop

**Local (stdio):** Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "overture-maps": {
      "command": "python",
      "args": ["-m", "overture_mcp.server"]
    }
  }
}
```

**Remote (SSE):** Connect to a hosted instance:

```json
{
  "mcpServers": {
    "overture-maps": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer your-api-key"
      }
    }
  }
}
```

## Example Agent Interaction

```
User: "Compare coffee shop density near two potential retail locations in Amsterdam"

Agent:
  1. Calls Geocoding MCP -> geocode("Leidseplein, Amsterdam") -> (52.3636, 4.8828)
  2. Calls Geocoding MCP -> geocode("De Pijp, Amsterdam") -> (52.3509, 4.8936)
  3. Calls Overture MCP -> get_place_categories({query: "coffee"})
  4. Calls Overture MCP -> count_places_by_type_in_radius(
       {lat: 52.3636, lng: 4.8828, radius_m: 500, category: "coffee_shop"}) -> 12
  5. Calls Overture MCP -> count_places_by_type_in_radius(
       {lat: 52.3509, lng: 4.8936, radius_m: 500, category: "coffee_shop"}) -> 7
  6. Returns: "Leidseplein has 12 coffee shops within 500m vs 7 in De Pijp..."
```

## Architecture

- **Runtime**: Python + FastMCP
- **Database**: DuckDB (in-process) with Spatial extension
- **Data**: Overture Maps GeoParquet on S3 (queried directly, no data copying)
- **Auth**: Bearer token via `Authorization` header (HTTP/SSE transports)
- **Transports**: stdio (local, default), SSE (hosted), Streamable HTTP (hosted)
- **Hosting**: Railway, Docker, or any container platform ($5-10/month)
- **Tool modes**: Direct (default, 13 tools) or progressive (3 meta-tools)

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical details and design decisions.

## Data Source

This server queries [Overture Maps](https://overturemaps.org/) data directly from S3.

- **Current release**: 2026-01-21.0
- **Update frequency**: Quarterly
- **License**: Overture Maps data is available under [ODbL](https://opendatacommons.org/licenses/odbl/) and [CDLA Permissive 2.0](https://cdla.dev/permissive-2-0/)
- **Coverage**: Global, with varying completeness by region
- **No AWS credentials needed** — the Overture S3 bucket is publicly accessible

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OVERTURE_API_KEY` | For SSE/HTTP | — | Bearer token for client auth |
| `TRANSPORT` | No | `stdio` | `stdio`, `sse`, or `http` |
| `TOOL_MODE` | No | `direct` | `direct` or `progressive` |
| `OVERTURE_DATA_VERSION` | No | `2026-01-21.0` | Overture release version |
| `MAX_CONCURRENT_QUERIES` | No | `3` | DuckDB concurrency limit |
| `MAX_RADIUS_M` | No | `50000` | Safety cap on radius (meters) |
| `PORT` | No | `8000` | Server port (SSE/HTTP only) |
| `HOST` | No | `0.0.0.0` | Server host (SSE/HTTP only) |

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Technical architecture and all design decisions
- [docs/TOOLS.md](docs/TOOLS.md) — MCP tool specifications
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — Operation catalog with full specs
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — Overture schema reference
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Railway deployment guide

## Contributing

Contributions welcome! Please read the architecture doc first to understand design decisions.

```bash
# Clone and set up dev environment
git clone https://github.com/your-username/overture-mcp-server.git
cd overture-mcp-server
pip install -e ".[dev]"

# Run tests (no S3 access needed)
pytest tests/ -m "not s3"

# Run full test suite
pytest tests/
```

## License

MIT
