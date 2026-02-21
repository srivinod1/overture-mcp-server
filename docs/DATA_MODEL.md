# Overture Maps Data Model Reference

This document describes the Overture Maps schema for the three data themes used in V1: Places, Buildings, and Divisions.

---

## Data Source

- **Bucket**: `s3://overturemaps-us-west-2`
- **Current Release**: `2026-01-21.0`
- **Format**: GeoParquet (cloud-optimized, columnar)
- **Access**: Public, no credentials required
- **Region**: `us-west-2`

### S3 Path Convention
```
s3://overturemaps-us-west-2/release/{VERSION}/theme={THEME}/type={TYPE}/
```

### Paths Used in V1
| Theme | S3 Path | Approx Size |
|-------|---------|-------------|
| Places | `theme=places/type=place/*` | ~5 GB |
| Buildings | `theme=buildings/type=building/*` | ~50 GB |
| Divisions | `theme=divisions/type=division_area/*` | ~2 GB |

---

## DuckDB Setup

### Extensions Required
```sql
INSTALL spatial;
LOAD spatial;
INSTALL httpfs;
LOAD httpfs;

SET s3_region='us-west-2';
```

### Reading Overture Data
```sql
-- Query places
SELECT * FROM read_parquet(
    's3://overturemaps-us-west-2/release/2026-01-21.0/theme=places/type=place/*'
) LIMIT 10;
```

---

## Theme: Places

### S3 Path
```
s3://overturemaps-us-west-2/release/2026-01-21.0/theme=places/type=place/*
```

### Key Columns

| Column | Type | Description | Used By |
|--------|------|-------------|---------|
| `id` | string | Unique place identifier | — |
| `names.primary` | string | Primary name of the place | `places_in_radius`, `nearest_place_of_type` |
| `categories.primary` | string | Primary category (e.g., "coffee_shop") | All place tools |
| `categories.alternate` | array[string] | Additional categories | `get_place_categories` |
| `geometry` | geometry (Point) | WKT point geometry | All place tools (spatial filter) |
| `bbox.xmin` | float | Bounding box min longitude | All tools (pre-filter) |
| `bbox.xmax` | float | Bounding box max longitude | All tools (pre-filter) |
| `bbox.ymin` | float | Bounding box min latitude | All tools (pre-filter) |
| `bbox.ymax` | float | Bounding box max latitude | All tools (pre-filter) |
| `confidence` | float | Data confidence score (0-1) | Future use |
| `websites` | array[string] | Associated websites | Future use |
| `phones` | array[string] | Phone numbers | Future use |
| `addresses` | struct | Address components | Future use |
| `sources` | array[struct] | Data source attribution | Future use |

### Category Taxonomy
Overture uses a hierarchical category system. Examples:
```
eat_and_drink
  eat_and_drink.restaurant
  eat_and_drink.coffee
    eat_and_drink.coffee.coffee_shop
    eat_and_drink.coffee.cafe
health
  health.hospital
  health.pharmacy
  health.dentist
financial_service
  financial_service.bank
  financial_service.atm
```

The `categories.primary` field contains the leaf-level category ID (e.g., `coffee_shop`, `hospital`).

### Sample Query: All Coffee Shops in 500m
```sql
-- Note: ST_Point takes (lng, lat), not (lat, lng)
-- Note: Uses ST_Distance_Spheroid for meter-accurate filtering, not ST_DWithin
SELECT
    names.primary AS name,
    categories.primary AS category,
    ST_Y(geometry) AS lat,
    ST_X(geometry) AS lng,
    CAST(ST_Distance_Spheroid(geometry, ST_Point(4.9041, 52.3676)) AS INTEGER) AS distance_m
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN 4.895 AND 4.913              -- bbox pre-filter (degrees)
  AND bbox.ymin BETWEEN 52.363 AND 52.372
  AND ST_Distance_Spheroid(geometry, ST_Point(4.9041, 52.3676)) < 500  -- exact filter (meters)
  AND categories.primary = 'coffee_shop'
ORDER BY distance_m ASC
LIMIT 20;
```

---

## Theme: Buildings

### S3 Path
```
s3://overturemaps-us-west-2/release/2026-01-21.0/theme=buildings/type=building/*
```

### Key Columns

| Column | Type | Description | Used By |
|--------|------|-------------|---------|
| `id` | string | Unique building identifier | — |
| `names.primary` | string | Building name (often null) | Future use |
| `class` | string | Building class: residential, commercial, industrial, etc. | `building_class_composition` |
| `height` | float | Building height in meters (often null) | Future use (v2) |
| `num_floors` | integer | Number of floors (often null) | Future use (v2) |
| `geometry` | geometry (Polygon) | Building footprint polygon | All building tools |
| `bbox.xmin` | float | Bounding box min longitude | All tools (pre-filter) |
| `bbox.xmax` | float | Bounding box max longitude | All tools (pre-filter) |
| `bbox.ymin` | float | Bounding box min latitude | All tools (pre-filter) |
| `bbox.ymax` | float | Bounding box max latitude | All tools (pre-filter) |
| `sources` | array[struct] | Data source attribution | — |

### Building Classes
Common values in the `class` column:
- `residential`
- `commercial`
- `industrial`
- `outbuilding`
- `agricultural`
- `transportation`
- `education`
- `medical`
- `government`

**Coverage note**: The `class` field is null for a significant percentage of buildings in many regions. The `building_class_composition` tool groups these as `unknown`.

### Sample Query: Building Composition in 1km
```sql
SELECT
    COALESCE(class, 'unknown') AS building_class,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=buildings/type=building/*')
WHERE bbox.xmin BETWEEN 4.890 AND 4.918                                -- bbox pre-filter
  AND bbox.ymin BETWEEN 52.358 AND 52.377
  AND ST_Distance_Spheroid(geometry, ST_Point(4.9041, 52.3676)) < 1000 -- exact filter (meters)
GROUP BY COALESCE(class, 'unknown')
ORDER BY count DESC;
```

---

## Theme: Divisions (Admin Boundaries)

### S3 Path
```
s3://overturemaps-us-west-2/release/2026-01-21.0/theme=divisions/type=division_area/*
```

### Key Columns

| Column | Type | Description | Used By |
|--------|------|-------------|---------|
| `id` | string | Unique boundary identifier | — |
| `names.primary` | string | Boundary name (e.g., "Amsterdam") | `point_in_admin_boundary` |
| `subtype` | string | Boundary type: country, region, county, locality, etc. | `point_in_admin_boundary` |
| `admin_level` | integer | OSM admin level (2=country, 4=region, 6=county, 8=city) | `point_in_admin_boundary` |
| `geometry` | geometry (Polygon/MultiPolygon) | Boundary polygon | `point_in_admin_boundary` |
| `bbox.xmin` | float | Bounding box min longitude | Pre-filter |
| `bbox.xmax` | float | Bounding box max longitude | Pre-filter |
| `bbox.ymin` | float | Bounding box min latitude | Pre-filter |
| `bbox.ymax` | float | Bounding box max latitude | Pre-filter |
| `parent_division_id` | string | ID of parent boundary | Future use (hierarchy) |

### Admin Levels
| Level | Type | Example |
|-------|------|---------|
| 2 | Country | Netherlands |
| 3 | — | (varies by country) |
| 4 | Region / State | North Holland / California |
| 5 | — | (varies by country) |
| 6 | County / District | — |
| 7 | — | (varies by country) |
| 8 | City / Municipality | Amsterdam |
| 9 | Sub-district | Amsterdam Centrum |
| 10 | Neighborhood | Jordaan |

### Sample Query: What Boundaries Contain a Point
```sql
SELECT
    names.primary AS name,
    admin_level,
    subtype
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=divisions/type=division_area/*')
WHERE bbox.xmin <= 4.9041 AND bbox.xmax >= 4.9041
  AND bbox.ymin <= 52.3676 AND bbox.ymax >= 52.3676
  AND ST_Contains(geometry, ST_Point(4.9041, 52.3676))
ORDER BY admin_level ASC;
```

---

## Performance Notes

### Bounding Box Pre-filter
Always include `bbox.*` filters before spatial functions. DuckDB uses Parquet row group statistics to skip irrelevant files, which dramatically reduces data read from S3.

### Radius to Bounding Box Conversion
For a search radius in meters, compute a rough bounding box delta:
```python
import math

def radius_to_bbox_delta(lat: float, radius_m: float) -> tuple[float, float]:
    """Convert radius in meters to approximate lat/lng deltas for bbox pre-filter."""
    lat_delta = radius_m / 111_320  # ~111km per degree latitude
    lng_delta = radius_m / (111_320 * math.cos(math.radians(lat)))
    return lat_delta, lng_delta
```

This is intentionally generous (slightly larger than the actual radius) to avoid clipping results. The precise `ST_Distance_Spheroid` filter handles exact distance checking in meters.

### Cold Start
First query after server start is slower (~5-10s) because DuckDB must:
1. Establish S3 connection
2. Read Parquet file metadata
3. Build internal column statistics

Subsequent queries benefit from metadata caching and are typically 1-3s.

### Data Size Implications
- **Places** (~5 GB): Fast queries, small individual records
- **Buildings** (~50 GB): Larger dataset, polygon geometries. Keep radius small for fast results.
- **Divisions** (~2 GB): Small dataset but large individual geometries (country boundaries are complex polygons). Point-in-polygon checks can be slow for complex boundaries.
