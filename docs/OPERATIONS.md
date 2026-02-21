# Operation Catalog

This document defines every operation available through `execute_operation`. Each operation includes its purpose, parameters, response schema, example, and underlying SQL pattern.

---

## Conventions

- Coordinates are `(lat, lng)` — latitude first, longitude second. Internally, `ST_Point` takes `(lng, lat)`. The server handles this conversion.
- All distances are in **meters**
- All operations return the [standard response envelope](TOOLS.md#tool-3-execute_operation)
- Maximum radius: 50,000m (50km)
- Maximum results: 100 per query
- Query timeout: 30 seconds
- All user-provided string values use parameterized queries (`?` placeholders). No string interpolation in SQL.
- Category values are validated against the cached taxonomy before reaching SQL.
- Spatial filtering uses bbox pre-filter (degrees) + `ST_Distance_Spheroid` (meters) — not `ST_DWithin`.
- When `include_geometry=true`, WKT strings are capped at 10,000 characters.

---

## Places Theme

### `get_place_categories`

Search and browse the Overture Maps place category taxonomy. Agents call this to discover valid category IDs before using other place operations.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | No | `null` | Text to search for in category names. Case-insensitive substring match. If omitted, returns top-level categories. |

**Response:**

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

**Notes:**
- Category list is loaded once on server startup and cached in memory.
- No S3 query at call time — <100ms latency.
- Returns max 50 categories per call.

---

### `places_in_radius`

Find all places matching a category within a radius of a point. Returns name, location, and distance for each place.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of center point (-180 to 180) |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |
| `category` | string | Yes | — | Overture category ID |
| `limit` | integer | No | `20` | Max results to return (1 to 100) |
| `include_geometry` | boolean | No | `false` | Include WKT geometry in results |

**Response:**

```json
{
  "results": [
    {
      "name": "Cafe De Jaren",
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

**Result object:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Place name (may be null if unnamed in Overture) |
| `category` | string | Overture category ID |
| `lat` | float | Latitude of the place |
| `lng` | float | Longitude of the place |
| `distance_m` | integer | Distance from query center point in meters |
| `geometry` | string | (Only if `include_geometry=true`) WKT geometry string |

**SQL pattern:**
```sql
SELECT
    names.primary AS name,
    categories.primary AS category,
    ST_Y(geometry) AS lat,
    ST_X(geometry) AS lng,
    CAST(ST_Distance_Spheroid(geometry, ST_Point(?, ?)) AS INTEGER) AS distance_m
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND ST_Distance_Spheroid(geometry, ST_Point(?, ?)) < ?
  AND categories.primary = ?
ORDER BY distance_m ASC
LIMIT ?
-- params: [lng, lat, lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m, category, limit]
```

**Empty result suggestion:**
`"No {category} found within {radius_m}m. Try increasing radius or check category with get_place_categories."`

---

### `nearest_place_of_type`

Find the single closest place of a given type to a point. Returns one result or none.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `category` | string | Yes | — | Overture category ID |
| `max_radius_m` | integer | No | `5000` | Maximum search radius in meters (1 to 50000) |
| `include_geometry` | boolean | No | `false` | Include WKT geometry in results |

**Response:**

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

**SQL pattern:**
Same as `places_in_radius` with `LIMIT 1`.

**Empty result suggestion:**
`"No {category} found within {max_radius_m}m. Try increasing max_radius_m."`

---

### `count_places_by_type_in_radius`

Count how many places of a category exist within a radius. Returns only the count.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |
| `category` | string | Yes | — | Overture category ID |

**Response:**

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

**SQL pattern:**
```sql
SELECT COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND ST_Distance_Spheroid(geometry, ST_Point(?, ?)) < ?
  AND categories.primary = ?
-- params: [lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m, category]
```

**Empty result suggestion:**
`"Zero {category} found within {radius_m}m. This may indicate sparse coverage in this region, or try a larger radius."`

---

## Buildings Theme

### `building_count_in_radius`

Count total buildings within a radius of a point.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |

**Response:**

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

**SQL pattern:**
```sql
SELECT COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=buildings/type=building/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND ST_Distance_Spheroid(geometry, ST_Point(?, ?)) < ?
-- params: [lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m]
```

**Empty result suggestion:**
`"Zero buildings found within {radius_m}m. This may be an undeveloped area or indicate sparse coverage in this region."`

---

### `building_class_composition`

Get the percentage breakdown of building types (residential, commercial, industrial, etc.) within a radius.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point |
| `lng` | float | Yes | — | Longitude of center point |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |

**Response:**

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

**Notes:**
- `unknown` captures buildings where Overture has no class data. This can be a significant percentage in some regions.
- The `percentage` values always sum to 100.0.

**SQL pattern:**
```sql
SELECT
    COALESCE(class, 'unknown') AS building_class,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=buildings/type=building/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND ST_Distance_Spheroid(geometry, ST_Point(?, ?)) < ?
GROUP BY COALESCE(class, 'unknown')
ORDER BY count DESC
-- params: [lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m]
```

**Empty result suggestion:**
`"Zero buildings found within {radius_m}m. Cannot compute composition for an area with no buildings."`

---

## Divisions Theme

### `point_in_admin_boundary`

Determine what administrative boundaries (country, region, city) contain a given point.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of the point |
| `lng` | float | Yes | — | Longitude of the point |

**Response:**

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

**Result object:**

| Field | Type | Description |
|-------|------|-------------|
| `locality` | string or null | City/town name (may be null for remote areas) |
| `region` | string or null | State/province/region name |
| `country` | string | Country name |
| `admin_levels` | array | Full hierarchy of administrative boundaries, ordered by admin level |

**Notes:**
- Admin levels follow the OpenStreetMap convention (2=country, 4=region, 6=county, 8=city, etc.).
- Some points (oceans, disputed territories) may return limited or no results.

**SQL pattern:**
```sql
SELECT
    names.primary AS name,
    admin_level,
    subtype
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=divisions/type=division_area/*')
WHERE bbox.xmin <= ? AND bbox.xmax >= ?
  AND bbox.ymin <= ? AND bbox.ymax >= ?
  AND ST_Contains(geometry, ST_Point(?, ?))
ORDER BY admin_level ASC
-- params: [lng, lng, lat, lat, lng, lat]
```

**Empty result suggestion:**
`"No administrative boundaries found for this point. It may be in international waters or an area with limited coverage."`
