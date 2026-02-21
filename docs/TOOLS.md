# Tool Specifications — V1

This document defines the complete specification for each tool in the Overture Maps MCP Server v1. Each tool is defined with its purpose, parameters, response schema, example queries, and the underlying SQL pattern.

---

## Conventions

**All tools follow these rules:**
- Coordinates are `(lat, lng)` — latitude first, longitude second
- All distances are in **meters**
- All tools return the [standard response envelope](#response-envelope)
- Maximum radius: 50,000m (50km)
- Maximum results: 100 per query
- Query timeout: 30 seconds

### Response Envelope

Every tool response wraps results in this structure:

```json
{
  "results": [],
  "count": 0,
  "query_params": {},
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `results` | array | Tool-specific result objects. Empty array for zero results. |
| `count` | integer | Number of results returned. |
| `query_params` | object | Echo of input parameters (helps agents verify what was queried). |
| `data_version` | string | Overture Maps release version used. |
| `suggestion` | string or null | Hint when results are empty (e.g., "Try increasing radius to 1000m."). Null when results exist. |

---

## Tool 1: `get_place_categories`

### Purpose
Search and browse the Overture Maps place category taxonomy. Agents call this to discover valid category IDs before calling other place tools.

### When to Use
- Agent needs to find the correct category ID for a user query like "coffee shop" or "hospital"
- Agent wants to explore what categories exist in a domain (e.g., all food-related categories)

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | No | `null` | Text to search for in category names. Case-insensitive substring match. If omitted, returns all top-level categories. |

### Response

```json
{
  "results": [
    {"category": "coffee_shop", "description": "A shop that primarily serves coffee"},
    {"category": "cafe", "description": "A casual dining establishment serving coffee, tea, and light meals"},
    {"category": "coffee_roaster", "description": "A business that roasts coffee beans"}
  ],
  "count": 3,
  "query_params": {"query": "coffee"},
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

### Result Object

| Field | Type | Description |
|-------|------|-------------|
| `category` | string | The Overture category ID. Use this value in other tool calls. |
| `description` | string | Human-readable description of the category. |

### Notes
- The category list is loaded once on server startup and cached in memory.
- No S3 query at call time — this tool is instant (<100ms).
- Returns max 50 categories per call. If `query` is omitted, returns top-level groupings.

---

## Tool 2: `places_in_radius`

### Purpose
Find all places matching a category within a radius of a point. Returns name, location, and distance for each place.

### When to Use
- "What coffee shops are near this location?"
- "Show me all hospitals within 2km"
- "Find pharmacies around this point"

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of center point (-180 to 180) |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |
| `category` | string | Yes | — | Overture category ID (use `get_place_categories` to discover) |
| `limit` | integer | No | `20` | Max results to return (1 to 100) |
| `include_geometry` | boolean | No | `false` | Include WKT geometry in results |

### Response

```json
{
  "results": [
    {
      "name": "Café De Jaren",
      "category": "cafe",
      "lat": 52.3683,
      "lng": 4.8957,
      "distance_m": 142
    },
    {
      "name": "Starbucks Rokin",
      "category": "coffee_shop",
      "lat": 52.3701,
      "lng": 4.8923,
      "distance_m": 287
    }
  ],
  "count": 2,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 500,
    "category": "cafe"
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

### Result Object

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Place name (may be null if unnamed in Overture) |
| `category` | string | Overture category ID |
| `lat` | float | Latitude of the place |
| `lng` | float | Longitude of the place |
| `distance_m` | integer | Distance from query center point in meters |
| `geometry` | string | (Only if `include_geometry=true`) WKT geometry string |

### SQL Pattern
```sql
SELECT
    names.primary AS name,
    categories.primary AS category,
    ST_Y(geometry) AS lat,
    ST_X(geometry) AS lng,
    CAST(ST_Distance_Spheroid(geometry, ST_Point({lng}, {lat})) AS INTEGER) AS distance_m
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN {lng_min} AND {lng_max}
  AND bbox.ymin BETWEEN {lat_min} AND {lat_max}
  AND ST_DWithin(geometry, ST_Point({lng}, {lat}), {radius_m})
  AND categories.primary = '{category}'
ORDER BY distance_m ASC
LIMIT {limit}
```

### Empty Result Suggestion
`"No {category} found within {radius_m}m. Try increasing radius or check category with get_place_categories."`

---

## Tool 3: `nearest_place_of_type`

### Purpose
Find the single closest place of a given type to a point. Returns one result or none.

### When to Use
- "Where's the nearest ATM?"
- "What's the closest hospital to this location?"
- "Find me the nearest gas station"

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `category` | string | Yes | — | Overture category ID |
| `max_radius_m` | integer | No | `5000` | Maximum search radius in meters (1 to 50000) |
| `include_geometry` | boolean | No | `false` | Include WKT geometry in results |

### Response

```json
{
  "results": [
    {
      "name": "ING Bank ATM",
      "category": "atm",
      "lat": 52.3691,
      "lng": 4.8988,
      "distance_m": 95
    }
  ],
  "count": 1,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "category": "atm",
    "max_radius_m": 5000
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

### SQL Pattern
Same as `places_in_radius` but with `LIMIT 1`.

### Empty Result Suggestion
`"No {category} found within {max_radius_m}m. The nearest one may be further away — try increasing max_radius_m."`

---

## Tool 4: `count_places_by_type_in_radius`

### Purpose
Count how many places of a category exist within a radius. Returns only the count — no individual place details.

### When to Use
- "How many restaurants are in this neighborhood?"
- "Is this area dense with banks?"
- Comparing counts between areas (call twice with different coordinates)

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |
| `category` | string | Yes | — | Overture category ID |

### Response

```json
{
  "results": [
    {
      "count": 23,
      "category": "restaurant",
      "radius_m": 1000
    }
  ],
  "count": 1,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 1000,
    "category": "restaurant"
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

### SQL Pattern
```sql
SELECT COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN {lng_min} AND {lng_max}
  AND bbox.ymin BETWEEN {lat_min} AND {lat_max}
  AND ST_DWithin(geometry, ST_Point({lng}, {lat}), {radius_m})
  AND categories.primary = '{category}'
```

### Empty Result Suggestion
`"Zero {category} found within {radius_m}m. This may indicate sparse Overture coverage in this region, or try a larger radius."`

---

## Tool 5: `building_count_in_radius`

### Purpose
Count total buildings within a radius of a point. No attribute filtering — just raw building count.

### When to Use
- "How built-up is this area?"
- "How many buildings are within 1km of this point?"
- Quick density check for urban vs rural assessment

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |

### Response

```json
{
  "results": [
    {
      "count": 847,
      "radius_m": 1000
    }
  ],
  "count": 1,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 1000
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

### SQL Pattern
```sql
SELECT COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=buildings/type=building/*')
WHERE bbox.xmin BETWEEN {lng_min} AND {lng_max}
  AND bbox.ymin BETWEEN {lat_min} AND {lat_max}
  AND ST_DWithin(geometry, ST_Point({lng}, {lat}), {radius_m})
```

### Empty Result Suggestion
`"Zero buildings found within {radius_m}m. This may be an undeveloped area or indicate sparse Overture building coverage in this region."`

---

## Tool 6: `building_class_composition`

### Purpose
Get the percentage breakdown of building types (residential, commercial, industrial, etc.) within a radius. This is spatial analytics that API wrappers cannot provide.

### When to Use
- "Is this area mostly residential or commercial?"
- "What's the mix of building types in this neighborhood?"
- Zoning and land-use analysis

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |

### Response

```json
{
  "results": [
    {
      "total_buildings": 847,
      "composition": {
        "residential": {"count": 551, "percentage": 65.1},
        "commercial": {"count": 212, "percentage": 25.0},
        "industrial": {"count": 42, "percentage": 5.0},
        "other": {"count": 25, "percentage": 3.0},
        "unknown": {"count": 17, "percentage": 2.0}
      },
      "radius_m": 1000
    }
  ],
  "count": 1,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 1000
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

### Notes
- `unknown` captures buildings where Overture has no class data. This can be a significant percentage in some regions.
- The `percentage` values always sum to 100.0.
- Building class taxonomy comes from Overture's `class` field on buildings.

### SQL Pattern
```sql
SELECT
    COALESCE(class, 'unknown') AS building_class,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=buildings/type=building/*')
WHERE bbox.xmin BETWEEN {lng_min} AND {lng_max}
  AND bbox.ymin BETWEEN {lat_min} AND {lat_max}
  AND ST_DWithin(geometry, ST_Point({lng}, {lat}), {radius_m})
GROUP BY COALESCE(class, 'unknown')
ORDER BY count DESC
```

### Empty Result Suggestion
`"Zero buildings found within {radius_m}m. Cannot compute composition for an area with no buildings."`

---

## Tool 7: `point_in_admin_boundary`

### Purpose
Determine what administrative boundaries (country, region, city) contain a given point. Answers "where is this?"

### When to Use
- "What city is this coordinate in?"
- "What country does this point fall in?"
- Adding geographic context to other tool results

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of the point |
| `lng` | float | Yes | — | Longitude of the point |

### Response

```json
{
  "results": [
    {
      "locality": "Amsterdam",
      "region": "North Holland",
      "country": "Netherlands",
      "admin_levels": [
        {"level": 2, "name": "Netherlands", "type": "country"},
        {"level": 4, "name": "North Holland", "type": "region"},
        {"level": 8, "name": "Amsterdam", "type": "locality"}
      ]
    }
  ],
  "count": 1,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

### Result Object

| Field | Type | Description |
|-------|------|-------------|
| `locality` | string or null | City/town name (may be null for remote areas) |
| `region` | string or null | State/province/region name |
| `country` | string | Country name |
| `admin_levels` | array | Full hierarchy of administrative boundaries, ordered by admin level |

### Notes
- This tool queries the divisions theme, which contains polygon geometries for admin boundaries.
- Admin levels follow the OpenStreetMap convention (2=country, 4=region, 6=county, 8=city, etc.).
- Some points (oceans, disputed territories) may return limited or no results.

### SQL Pattern
```sql
SELECT
    names.primary AS name,
    admin_level,
    subtype
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=divisions/type=division_area/*')
WHERE bbox.xmin <= {lng} AND bbox.xmax >= {lng}
  AND bbox.ymin <= {lat} AND bbox.ymax >= {lat}
  AND ST_Contains(geometry, ST_Point({lng}, {lat}))
ORDER BY admin_level ASC
```

### Empty Result Suggestion
`"No administrative boundaries found for this point. It may be in international waters or an area with limited Overture coverage."`

---

## Error Responses

Tools return errors in this format when input validation fails:

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

### Common Errors

| Error | Cause |
|-------|-------|
| `"lat must be between -90 and 90"` | Invalid latitude |
| `"lng must be between -180 and 180"` | Invalid longitude |
| `"radius_m must be between 1 and 50000"` | Radius out of bounds |
| `"Unknown category: {x}. Use get_place_categories to find valid categories."` | Invalid category ID |
| `"Query timeout after 30s. Try a smaller radius."` | S3 query took too long |
