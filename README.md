# Overture Maps MCP Server

An open-source MCP server that exposes [Overture Maps](https://overturemaps.org/) data as spatial analytics tools for AI agents.

## What This Does

AI agents need geospatial intelligence. This server gives them direct access to Overture Maps data through clean, composable tool primitives.

**Ask questions like:**
- "How many coffee shops are within 500m of this location?"
- "What's the building composition (residential vs commercial) in this area?"
- "What city/country does this coordinate fall in?"
- "What are the nearest hospitals to this point?"

## How It Fits in the Agent Stack

```
┌─────────────────────────────────────────────────┐
│  AI Agent (Claude, etc.)                        │
├─────────────────┬───────────────────────────────┤
│  Geocoding /    │  Overture Maps MCP            │
│  Routing MCP    │  ──────────────────           │
│  ─────────────  │  Place analytics              │
│  Geocoding      │  Building composition         │
│  Routing        │  Admin boundary lookups       │
│  Directions     │  Density analysis             │
│  ETA            │  Category discovery           │
└─────────────────┴───────────────────────────────┘
```

**Overture MCP** handles spatial analytics that need direct data access.
**Geocoding/Routing MCPs** handle geocoding, routing, and directions via APIs.

They're complementary — use them together for a complete geospatial agent.

## Available Tools (V1)

| Tool | What It Does |
|------|-------------|
| `get_place_categories` | Search Overture's place category taxonomy |
| `places_in_radius` | Find all places matching a category within a radius |
| `nearest_place_of_type` | Find the single closest place of a given type |
| `count_places_by_type_in_radius` | Count places of a category in an area |
| `building_count_in_radius` | Count buildings in an area |
| `building_class_composition` | Get % breakdown of building types (residential/commercial/industrial) |
| `point_in_admin_boundary` | Find what country/region/city contains a point |

See [docs/TOOLS.md](docs/TOOLS.md) for detailed specifications.

## Quick Start

### Prerequisites
- Python 3.10+
- An MCP-compatible AI agent

### Install

```bash
pip install overture-mcp-server
```

### Run Locally

```bash
export OVERTURE_API_KEY="your-api-key"
python -m overture_mcp.server
```

The server starts on `http://localhost:8000` with SSE transport.

### Connect from Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "overture-maps": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

### Connect to Hosted Instance

```json
{
  "mcpServers": {
    "overture-maps": {
      "url": "https://your-railway-instance.up.railway.app/sse",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

## Example Agent Interaction

```
User: "Are there any good coffee options near the Rijksmuseum in Amsterdam?"

Agent:
  1. Calls Geocoding MCP → geocode("Rijksmuseum, Amsterdam") → (52.3600, 4.8852)
  2. Calls Overture MCP → get_place_categories(query="coffee") → ["coffee_shop", "cafe", ...]
  3. Calls Overture MCP → places_in_radius(lat=52.36, lng=4.8852, radius_m=500, category="coffee_shop")
  4. Returns: "I found 8 coffee shops within 500m of the Rijksmuseum: ..."
```

## Architecture

- **Runtime**: Python + FastMCP
- **Database**: DuckDB (in-process) with Spatial extension
- **Data**: Overture Maps GeoParquet on S3 (queried directly, no data copying)
- **Auth**: API key via `X-API-Key` header
- **Hosting**: Railway ($5-10/month)

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical details and design decisions.

## Data Source

This server queries [Overture Maps](https://overturemaps.org/) data directly from S3.

- **Current release**: 2026-01-21.0
- **Update frequency**: Quarterly
- **License**: Overture Maps data is available under [ODbL](https://opendatacommons.org/licenses/odbl/) and [CDLA Permissive 2.0](https://cdla.dev/permissive-2-0/)
- **Coverage**: Global, with varying completeness by region

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Technical architecture and all design decisions
- [docs/TOOLS.md](docs/TOOLS.md) — Detailed tool specifications with examples
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — Overture schema reference
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Railway deployment guide

## Contributing

Contributions welcome! Please read the architecture doc first to understand design decisions.

```bash
# Clone and set up dev environment
git clone https://github.com/your-org/overture-mcp-server.git
cd overture-mcp-server
pip install -e ".[dev]"

# Run tests
pytest tests/
```

## License

MIT
