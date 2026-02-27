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
- **DuckDB coordinate order quirk**: `ST_Distance_Spheroid` expects (lat, lng) internally, but Overture stores (lng, lat). All geometry arguments to `ST_Distance_Spheroid` are wrapped in `ST_FlipCoordinates()` to correct coordinate order. Without this, distance calculations return incorrect values. This does NOT apply to `ST_Contains`, which operates in coordinate space.
- **Polygon geometry quirk**: `ST_FlipCoordinates` can only operate on point geometries. For buildings and land use (which have polygon footprints), use `ST_FlipCoordinates(ST_Centroid(geometry))` to extract the center point first. Places use point geometries, so `ST_FlipCoordinates(geometry)` works directly.
- **LineString geometry quirk**: For transportation segments (LineString), use `ST_FlipCoordinates(ST_PointOnSurface(geometry))` to get a point guaranteed to lie on the line. `ST_PointOnSurface` is preferred over `ST_Centroid` for line geometries because the centroid of a curved road may fall off the line.
- **Point-in-polygon operations** (`point_in_admin_boundary`, `land_use_at_point`) use `ST_Contains(geometry, ST_Point(lng, lat))`. No `ST_FlipCoordinates` needed — `ST_Contains` operates in coordinate space.
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
    {"category": "cafe", "description": "A casual dining establishment serving coffee, tea, and light meals"},
    {"category": "coffee_shop", "description": "A shop that primarily serves coffee"},
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
| `include_closed` | boolean | No | `false` | Include permanently closed places (excluded by default) |

**Response:**

```json
{
  "results": [
    {
      "name": "Cafe De Jaren",
      "category": "cafe",
      "lat": 52.3683,
      "lng": 4.8957,
      "distance_m": 142,
      "confidence": 0.92,
      "address": "Nieuwe Doelenstraat 20, 1012 CP Amsterdam, Netherlands",
      "phone": "+31 20 625 5771",
      "website": "https://cafedejaren.nl",
      "brand": null
    },
    {
      "name": "Brew & Co. Rokin",
      "category": "cafe",
      "lat": 52.3701,
      "lng": 4.8923,
      "distance_m": 287,
      "confidence": 0.96,
      "address": "Rokin 70, 1012 KW Amsterdam, Netherlands",
      "phone": null,
      "website": null,
      "brand": {"name": "Brew & Co.", "wikidata": "Q99999999"}
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
| `confidence` | float | Overture data quality score (0.0 to 1.0). Higher is better. |
| `address` | string or null | Freeform address string. Composed from Overture's structured address fields (freeform, locality, postcode, region, country). |
| `phone` | string or null | Primary phone number (first from Overture's phones array). |
| `website` | string or null | Primary website URL (first from Overture's websites array). |
| `brand` | object or null | Brand info if this is a chain location. Contains `name` (string) and `wikidata` (string, Wikidata entity ID). |
| `geometry` | string | (Only if `include_geometry=true`) WKT geometry string |

**SQL pattern:**
```sql
SELECT
    names."primary" AS name,
    categories."primary" AS category,
    ST_Y(geometry) AS lat,
    ST_X(geometry) AS lng,
    CAST(ST_Distance_Spheroid(
        ST_FlipCoordinates(geometry),
        ST_FlipCoordinates(ST_Point(?, ?))
    ) AS INTEGER) AS distance_m,
    confidence,
    addresses,
    phones,
    websites,
    brand.names."primary" AS brand_name,
    brand.wikidata AS brand_wikidata
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(geometry),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
  AND categories."primary" = ?
  AND COALESCE(operating_status, 'open') != 'permanently_closed'  -- excluded by default
ORDER BY distance_m ASC
LIMIT ?
-- params: [lng, lat, lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m, category, limit]
```

**Address construction:** The `address` result field is constructed from Overture's structured `addresses` column. If `addresses[1].freeform` exists, it is used as the base. Otherwise, the address is composed from `locality`, `postcode`, `region`, `country` fields. If no address data is available, the field is null.

**Operating status filter:** By default, places with `operating_status = 'permanently_closed'` are excluded. Temporarily closed places are included (they're still relevant for site selection). Pass `include_closed=true` to include all places.

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
| `include_closed` | boolean | No | `false` | Include permanently closed places (excluded by default) |

**Response:**

```json
{
  "results": [
    {
      "name": "ING Bank ATM",
      "category": "atm",
      "lat": 52.3691,
      "lng": 4.8988,
      "distance_m": 95,
      "confidence": 0.88,
      "address": "Rokin 51, 1012 KK Amsterdam, Netherlands",
      "phone": null,
      "website": null,
      "brand": {"name": "ING", "wikidata": "Q645708"}
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

**Result object:** Same as `places_in_radius` (includes `confidence`, `address`, `phone`, `website`, `brand`).

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
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(geometry),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
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
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_Centroid(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
-- params: [lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m]
```

**Note:** Buildings have polygon geometries (footprints), not points. `ST_FlipCoordinates` cannot operate on polygons directly, so `ST_Centroid(geometry)` extracts the center point first.

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
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_Centroid(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
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

---

## Transportation Theme

### `road_count_by_class`

Count road segments grouped by road class within a radius of a point. Useful for understanding road network density and composition.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of center point (-180 to 180) |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |

**Response:**

```json
{
  "results": [
    {
      "total_segments": 142,
      "by_class": {
        "residential": {"count": 68, "percentage": 47.9},
        "service": {"count": 31, "percentage": 21.8},
        "tertiary": {"count": 18, "percentage": 12.7},
        "secondary": {"count": 12, "percentage": 8.5},
        "footway": {"count": 8, "percentage": 5.6},
        "cycleway": {"count": 5, "percentage": 3.5}
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
- Only includes `subtype = 'road'` segments (excludes rail and water).
- Road classes follow the Overture/OSM hierarchy: `motorway`, `trunk`, `primary`, `secondary`, `tertiary`, `residential`, `service`, `footway`, `cycleway`, `path`, `track`, `unclassified`.
- Segments with null class are counted as `"unknown"`.
- Percentage values sum to 100.0.

**SQL pattern:**
```sql
SELECT
    COALESCE(class, 'unknown') AS road_class,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=transportation/type=segment/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND subtype = 'road'
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_PointOnSurface(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
GROUP BY COALESCE(class, 'unknown')
ORDER BY count DESC
-- params: [lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m]
```

**Empty result suggestion:**
`"Zero road segments found within {radius_m}m. This may be an undeveloped area or an area with limited road mapping."`

---

### `nearest_road_of_class`

Find the single closest road segment of a given class to a point. Returns the road name, class, surface, distance, and flags.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of center point (-180 to 180) |
| `road_class` | string | Yes | — | Road class (e.g., `residential`, `primary`, `motorway`) |
| `max_radius_m` | integer | No | `5000` | Maximum search radius in meters (1 to 50000) |
| `include_geometry` | boolean | No | `false` | Include WKT geometry in results |

**Response:**

```json
{
  "results": [
    {
      "name": "Damrak",
      "road_class": "secondary",
      "road_surface": "asphalt",
      "distance_m": 78,
      "lat": 52.3741,
      "lng": 4.8936,
      "is_bridge": false,
      "is_tunnel": false,
      "is_link": false
    }
  ],
  "count": 1,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "road_class": "secondary",
    "max_radius_m": 5000
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

**Result object:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string or null | Road name (null for unnamed segments) |
| `road_class` | string | Road class (e.g., `residential`, `primary`) |
| `road_surface` | string or null | Surface type (e.g., `paved`, `asphalt`, `gravel`). Null if unknown. |
| `distance_m` | integer | Distance from query center to nearest point on the road segment |
| `lat` | float | Latitude of the nearest point on the segment |
| `lng` | float | Longitude of the nearest point on the segment |
| `is_bridge` | boolean | Whether this segment is a bridge |
| `is_tunnel` | boolean | Whether this segment is a tunnel |
| `is_link` | boolean | Whether this is a highway ramp/link |
| `geometry` | string | (Only if `include_geometry=true`) WKT LineString geometry |

**Notes:**
- `road_class` is validated against a known set of values before reaching SQL (same pattern as category validation for places).
- `road_surface` may be null for ~40-60% of segments depending on region.
- Distance is measured from the center point to the nearest point on the road geometry (via `ST_PointOnSurface`).

**SQL pattern:**
```sql
SELECT
    names."primary" AS name,
    class AS road_class,
    road_surface,
    CAST(ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_PointOnSurface(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
    ) AS INTEGER) AS distance_m,
    ST_Y(ST_PointOnSurface(geometry)) AS lat,
    ST_X(ST_PointOnSurface(geometry)) AS lng,
    COALESCE(road_flags.is_bridge, false) AS is_bridge,
    COALESCE(road_flags.is_tunnel, false) AS is_tunnel,
    COALESCE(road_flags.is_link, false) AS is_link
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=transportation/type=segment/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND subtype = 'road'
  AND class = ?
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_PointOnSurface(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
ORDER BY distance_m ASC
LIMIT 1
-- params: [lng, lat, lng_min, lng_max, lat_min, lat_max, road_class, lng, lat, max_radius_m]
```

**Empty result suggestion:**
`"No {road_class} road found within {max_radius_m}m. Try increasing max_radius_m or use a more common road class."`

---

### `road_surface_composition`

Get the percentage breakdown of road surface types within a radius. Useful for infrastructure quality assessment.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of center point (-180 to 180) |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |

**Response:**

```json
{
  "results": [
    {
      "total_segments": 142,
      "composition": {
        "paved": {"count": 45, "percentage": 31.7},
        "asphalt": {"count": 38, "percentage": 26.8},
        "cobblestone": {"count": 8, "percentage": 5.6},
        "unknown": {"count": 51, "percentage": 35.9}
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
- Only includes `subtype = 'road'` segments.
- `unknown` captures segments where `road_surface` is null. This is often a large percentage (40-60% in many regions).
- Road surface values include: `paved`, `unpaved`, `asphalt`, `concrete`, `gravel`, `dirt`, `ground`, `cobblestone`, and others.
- Percentage values sum to 100.0.

**SQL pattern:**
```sql
SELECT
    COALESCE(road_surface, 'unknown') AS surface_type,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=transportation/type=segment/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND subtype = 'road'
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_PointOnSurface(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
GROUP BY COALESCE(road_surface, 'unknown')
ORDER BY count DESC
-- params: [lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m]
```

**Empty result suggestion:**
`"Zero road segments found within {radius_m}m. Cannot compute surface composition for an area with no roads."`

---

## Land Use Theme

### `land_use_at_point`

Determine the land use designation at a specific point. Returns all land use polygons that contain the point (a point may be in multiple overlapping zones).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of the point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of the point (-180 to 180) |

**Response:**

```json
{
  "results": [
    {
      "subtype": "residential",
      "class": "apartments",
      "names_primary": "Grachtengordel-West",
      "source": "OpenStreetMap"
    },
    {
      "subtype": "park",
      "class": "urban_park",
      "names_primary": null,
      "source": "OpenStreetMap"
    }
  ],
  "count": 2,
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
| `subtype` | string | Land use subtype (22 values: `residential`, `commercial`, `industrial`, `park`, `agriculture`, etc.) |
| `class` | string or null | More specific land use class (95+ values, e.g., `retail`, `office`, `apartments`, `urban_park`) |
| `names_primary` | string or null | Name of the land use zone (often null) |
| `source` | string | Data source (typically `"OpenStreetMap"`) |

**Notes:**
- A single point may return multiple overlapping land use polygons (e.g., a park inside a residential zone). All matches are returned.
- Uses `ST_Contains` (point-in-polygon) — no `ST_FlipCoordinates` needed.
- Land use subtypes: `residential`, `commercial`, `industrial`, `institutional`, `agriculture`, `aquaculture`, `recreation`, `park`, `forest`, `cemetery`, `religious`, `military`, `education`, `medical`, `transportation`, `airport`, `port`, `dam`, `quarry`, `landfill`, `brownfield`, `greenfield`.

**SQL pattern:**
```sql
SELECT
    subtype,
    class,
    names."primary" AS names_primary,
    sources[1].dataset AS source
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=base/type=land_use/*')
WHERE bbox.xmin <= ? AND bbox.xmax >= ?
  AND bbox.ymin <= ? AND bbox.ymax >= ?
  AND ST_Contains(geometry, ST_Point(?, ?))
-- params: [lng, lng, lat, lat, lng, lat]
```

**Empty result suggestion:**
`"No land use designation found for this point. The area may lack land use mapping coverage, or the point may be in water/unmapped territory."`

---

### `land_use_composition`

Get the percentage breakdown of land use types within a radius. Useful for area characterization (is this predominantly residential, commercial, mixed-use?).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of center point (-180 to 180) |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |

**Response:**

```json
{
  "results": [
    {
      "total_parcels": 34,
      "composition": {
        "residential": {"count": 15, "percentage": 44.1},
        "commercial": {"count": 8, "percentage": 23.5},
        "park": {"count": 5, "percentage": 14.7},
        "institutional": {"count": 3, "percentage": 8.8},
        "industrial": {"count": 2, "percentage": 5.9},
        "education": {"count": 1, "percentage": 2.9}
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
- Groups by `subtype` (not `class`) for a manageable number of categories.
- Uses centroid-based distance (same pattern as buildings — `ST_FlipCoordinates(ST_Centroid(geometry))`).
- Percentage values sum to 100.0.
- A land use parcel is counted once based on its centroid position, even if the polygon extends beyond the radius.

**SQL pattern:**
```sql
SELECT
    subtype,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=base/type=land_use/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_Centroid(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
GROUP BY subtype
ORDER BY count DESC
-- params: [lng_min, lng_max, lat_min, lat_max, lng, lat, radius_m]
```

**Empty result suggestion:**
`"Zero land use parcels found within {radius_m}m. This area may lack land use mapping coverage. Try increasing radius."`

---

### `land_use_search`

Find land use parcels of a specific subtype within a radius. Useful for locating specific types of zones (e.g., "where are the parks near here?").

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `lat` | float | Yes | — | Latitude of center point (-90 to 90) |
| `lng` | float | Yes | — | Longitude of center point (-180 to 180) |
| `radius_m` | integer | Yes | — | Search radius in meters (1 to 50000) |
| `subtype` | string | Yes | — | Land use subtype (e.g., `residential`, `park`, `commercial`) |
| `limit` | integer | No | `20` | Max results to return (1 to 100) |
| `include_geometry` | boolean | No | `false` | Include WKT geometry in results |

**Response:**

```json
{
  "results": [
    {
      "subtype": "park",
      "class": "urban_park",
      "names_primary": "Vondelpark",
      "lat": 52.3579,
      "lng": 4.8686,
      "distance_m": 1245
    },
    {
      "subtype": "park",
      "class": null,
      "names_primary": "Sarphatipark",
      "lat": 52.3545,
      "lng": 4.8919,
      "distance_m": 1823
    }
  ],
  "count": 2,
  "query_params": {
    "lat": 52.3676,
    "lng": 4.9041,
    "radius_m": 2000,
    "subtype": "park"
  },
  "data_version": "2026-01-21.0",
  "suggestion": null
}
```

**Result object:**

| Field | Type | Description |
|-------|------|-------------|
| `subtype` | string | Land use subtype |
| `class` | string or null | More specific land use class |
| `names_primary` | string or null | Name of the land use zone |
| `lat` | float | Latitude of the parcel centroid |
| `lng` | float | Longitude of the parcel centroid |
| `distance_m` | integer | Distance from query center to parcel centroid in meters |
| `geometry` | string | (Only if `include_geometry=true`) WKT Polygon geometry |

**Notes:**
- `subtype` is validated against a known set of values before reaching SQL (same pattern as category validation for places).
- Distance is measured to the centroid of the land use polygon.
- Results are ordered by distance ascending.

**SQL pattern:**
```sql
SELECT
    subtype,
    class,
    names."primary" AS names_primary,
    ST_Y(ST_Centroid(geometry)) AS lat,
    ST_X(ST_Centroid(geometry)) AS lng,
    CAST(ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_Centroid(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
    ) AS INTEGER) AS distance_m
FROM read_parquet('s3://overturemaps-us-west-2/release/{version}/theme=base/type=land_use/*')
WHERE bbox.xmin BETWEEN ? AND ?
  AND bbox.ymin BETWEEN ? AND ?
  AND subtype = ?
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_Centroid(geometry)),
        ST_FlipCoordinates(ST_Point(?, ?))
      ) < ?
ORDER BY distance_m ASC
LIMIT ?
-- params: [lng, lat, lng_min, lng_max, lat_min, lat_max, subtype, lng, lat, radius_m, limit]
```

**Empty result suggestion:**
`"No {subtype} land use found within {radius_m}m. Try increasing radius or use land_use_composition to see what land use types exist in this area."`
