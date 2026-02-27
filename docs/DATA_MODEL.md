# Overture Maps Data Model Reference

This document describes the Overture Maps schema for the five data themes used in V1: Places, Buildings, Divisions, Transportation, and Land Use.

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
| Transportation | `theme=transportation/type=segment/*` | ~46 GB |
| Land Use | `theme=base/type=land_use/*` | ~3 GB |

**Note:** Land Use lives under the `base` theme (not a dedicated top-level theme). Transportation uses only `type=segment` (not `type=connector`).

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
| `categories.primary` | string | Primary category (e.g., "cafe") | All place tools |
| `categories.alternate` | array[string] | Additional categories | `get_place_categories` |
| `geometry` | geometry (Point) | WKT point geometry | All place tools (spatial filter) |
| `bbox.xmin` | float | Bounding box min longitude | All tools (pre-filter) |
| `bbox.xmax` | float | Bounding box max longitude | All tools (pre-filter) |
| `bbox.ymin` | float | Bounding box min latitude | All tools (pre-filter) |
| `bbox.ymax` | float | Bounding box max latitude | All tools (pre-filter) |
| `confidence` | float | Data quality score (0.0 to 1.0). Higher = more reliable. | `places_in_radius`, `nearest_place_of_type` |
| `websites` | array[string] | Associated website URLs | `places_in_radius`, `nearest_place_of_type` |
| `phones` | array[string] | Phone numbers | `places_in_radius`, `nearest_place_of_type` |
| `addresses` | array[struct] | Structured address components (see below) | `places_in_radius`, `nearest_place_of_type` |
| `brand.names.primary` | string | Brand name (for chain locations) | `places_in_radius`, `nearest_place_of_type` |
| `brand.wikidata` | string | Wikidata entity ID for the brand | `places_in_radius`, `nearest_place_of_type` |
| `operating_status` | string | Required field: `open`, `temporarily_closed`, or `permanently_closed` | All place tools (default filter) |
| `sources` | array[struct] | Data source attribution | — |

### Address Structure

The `addresses` column is an array of structs. Each struct has:

| Field | Type | Description |
|-------|------|-------------|
| `freeform` | string | Full address as a single string (most useful field) |
| `locality` | string | City/town name |
| `postcode` | string | Postal/zip code |
| `region` | string | State/province |
| `country` | string | ISO 3166-1 alpha-2 country code |

The server uses `addresses[1]` (first address entry). If `freeform` is available, it is used directly. Otherwise, the address is composed from `locality`, `postcode`, `region`, `country`.

### Brand Structure

The `brand` column identifies chain/franchise locations:

| Field | Type | Description |
|-------|------|-------------|
| `brand.names.primary` | string | Brand display name |
| `brand.wikidata` | string | Wikidata entity ID (e.g., "Q37158"). Enables cross-referencing. |

### Operating Status

The `operating_status` field is required (never null) in Overture Places:
- `open` — currently operating (vast majority of records)
- `temporarily_closed` — closed but expected to reopen
- `permanently_closed` — permanently shut down

By default, V1 place queries exclude `permanently_closed` places. The `include_closed=true` parameter overrides this.

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

The `categories.primary` field contains the leaf-level category ID (e.g., `cafe`, `hospital`).

### Sample Query: All Cafes in 500m
```sql
-- Note: ST_Point takes (lng, lat), not (lat, lng)
-- Note: Uses ST_Distance_Spheroid for meter-accurate filtering, not ST_DWithin
-- Note: ST_FlipCoordinates swaps (lng,lat) → (lat,lng) for ST_Distance_Spheroid
SELECT
    names.primary AS name,
    categories.primary AS category,
    ST_Y(geometry) AS lat,
    ST_X(geometry) AS lng,
    CAST(ST_Distance_Spheroid(
        ST_FlipCoordinates(geometry),
        ST_FlipCoordinates(ST_Point(4.9041, 52.3676))
    ) AS INTEGER) AS distance_m
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN 4.895 AND 4.913              -- bbox pre-filter (degrees)
  AND bbox.ymin BETWEEN 52.363 AND 52.372
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(geometry),
        ST_FlipCoordinates(ST_Point(4.9041, 52.3676))
      ) < 500                                         -- exact filter (meters)
  AND categories.primary = 'cafe'
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
-- Note: Buildings have polygon geometries, so ST_Centroid extracts the center point
-- before ST_FlipCoordinates swaps (lng,lat) → (lat,lng) for ST_Distance_Spheroid
SELECT
    COALESCE(class, 'unknown') AS building_class,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=buildings/type=building/*')
WHERE bbox.xmin BETWEEN 4.890 AND 4.918                                -- bbox pre-filter
  AND bbox.ymin BETWEEN 52.358 AND 52.377
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_Centroid(geometry)),
        ST_FlipCoordinates(ST_Point(4.9041, 52.3676))
      ) < 1000                                                         -- exact filter (meters)
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

## Theme: Transportation (Road Segments)

### S3 Path
```
s3://overturemaps-us-west-2/release/2026-01-21.0/theme=transportation/type=segment/*
```

### Key Columns

| Column | Type | Description | Used By |
|--------|------|-------------|---------|
| `id` | string | Unique segment identifier | — |
| `names.primary` | string | Road name (often null for minor roads) | `nearest_road_of_class` |
| `subtype` | string | Segment type: `road`, `rail`, `water` | All (filter to `road` only) |
| `class` | string | Road class (see below) | `road_count_by_class`, `nearest_road_of_class` |
| `road_surface` | string | Surface material (see below) | `road_surface_composition`, `nearest_road_of_class` |
| `road_flags.is_bridge` | boolean | Whether segment is a bridge | `nearest_road_of_class` |
| `road_flags.is_tunnel` | boolean | Whether segment is a tunnel | `nearest_road_of_class` |
| `road_flags.is_link` | boolean | Whether segment is a highway ramp/link | `nearest_road_of_class` |
| `road_flags.is_under_construction` | boolean | Whether road is under construction | — |
| `geometry` | geometry (LineString) | Road centerline geometry | All transportation tools |
| `bbox.xmin` | float | Bounding box min longitude | All tools (pre-filter) |
| `bbox.xmax` | float | Bounding box max longitude | All tools (pre-filter) |
| `bbox.ymin` | float | Bounding box min latitude | All tools (pre-filter) |
| `bbox.ymax` | float | Bounding box max latitude | All tools (pre-filter) |
| `speed_limits` | array[struct] | Speed limit data (sparse, ~10-15% globally) | Excluded from V1 |
| `width_rules` | array[struct] | Road width rules (very sparse) | Excluded from V1 |
| `access_restrictions` | array[struct] | Access rules (sparse outside Europe) | Excluded from V1 |
| `sources` | array[struct] | Data source attribution | — |

### Road Classes

The `class` field follows the OpenStreetMap road hierarchy. V1 validates against this set:

| Class | Description | Typical Use |
|-------|-------------|-------------|
| `motorway` | Controlled-access highway | Major highways, interstates |
| `trunk` | Important roads that aren't motorways | National highways |
| `primary` | Major roads | State highways, arterials |
| `secondary` | Less important through roads | County roads |
| `tertiary` | Local connecting roads | Town roads |
| `residential` | Roads in residential areas | Neighborhood streets |
| `service` | Access roads, parking lots, driveways | Service roads |
| `footway` | Designated foot paths | Sidewalks, pedestrian paths |
| `cycleway` | Designated bicycle paths | Bike lanes, cycle tracks |
| `path` | Multi-use paths | Hiking trails, shared-use paths |
| `track` | Agricultural/forestry roads | Farm roads |
| `unclassified` | Minor public roads | Miscellaneous |

### Road Surface Types

Common values for `road_surface`:

| Surface | Description |
|---------|-------------|
| `paved` | Generic paved (asphalt, concrete, etc.) |
| `unpaved` | Generic unpaved |
| `asphalt` | Asphalt/bitumen surface |
| `concrete` | Concrete surface |
| `gravel` | Gravel/crushed stone |
| `dirt` | Dirt/earth road |
| `ground` | Natural ground surface |
| `cobblestone` | Cobblestone/sett surface |

**Coverage note**: `road_surface` is null for ~40-60% of segments globally, depending on region. European cities tend to have better coverage than rural areas in developing regions.

### Sample Query: Road Network Composition in 1km
```sql
-- Note: Road segments are LineStrings. ST_PointOnSurface returns a point
-- guaranteed to lie on the line (more robust than ST_Centroid for curves).
SELECT
    COALESCE(class, 'unknown') AS road_class,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=transportation/type=segment/*')
WHERE bbox.xmin BETWEEN 4.890 AND 4.918
  AND bbox.ymin BETWEEN 52.358 AND 52.377
  AND subtype = 'road'
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_PointOnSurface(geometry)),
        ST_FlipCoordinates(ST_Point(4.9041, 52.3676))
      ) < 1000
GROUP BY COALESCE(class, 'unknown')
ORDER BY count DESC;
```

---

## Theme: Land Use

### S3 Path
```
s3://overturemaps-us-west-2/release/2026-01-21.0/theme=base/type=land_use/*
```

**Important:** Land use is under the `base` theme, not a dedicated top-level theme. This is an Overture Maps organizational choice. The `base` theme also contains `land` (natural terrain) and `land_cover` (satellite-derived) types, which are not used in V1.

### Key Columns

| Column | Type | Description | Used By |
|--------|------|-------------|---------|
| `id` | string | Unique land use parcel identifier | — |
| `names.primary` | string | Name of the land use zone (often null) | `land_use_at_point`, `land_use_search` |
| `subtype` | string | Land use category (22 values, see below) | All land use tools |
| `class` | string | More specific classification (95+ values) | All land use tools |
| `geometry` | geometry (Polygon/MultiPolygon) | Land use area boundary | All land use tools |
| `bbox.xmin` | float | Bounding box min longitude | All tools (pre-filter) |
| `bbox.xmax` | float | Bounding box max longitude | All tools (pre-filter) |
| `bbox.ymin` | float | Bounding box min latitude | All tools (pre-filter) |
| `bbox.ymax` | float | Bounding box max latitude | All tools (pre-filter) |
| `sources` | array[struct] | Data source (typically OpenStreetMap) | `land_use_at_point` |

### Land Use Subtypes

The `subtype` field has 22 possible values. These are the primary categories used by `land_use_composition`:

| Subtype | Description | Typical Class Values |
|---------|-------------|---------------------|
| `residential` | Housing areas | `apartments`, `houses`, `detached`, `allotments` |
| `commercial` | Business areas | `retail`, `office`, `hotel`, `shopping_centre` |
| `industrial` | Manufacturing/warehousing | `warehouse`, `factory`, `depot` |
| `institutional` | Government/civic buildings | `government`, `civic` |
| `agriculture` | Farming land | `farmland`, `orchard`, `vineyard`, `greenhouse_horticulture` |
| `aquaculture` | Fish/shellfish farming | `fish_farm` |
| `recreation` | Recreational areas | `pitch`, `playground`, `golf_course`, `swimming_pool` |
| `park` | Parks and gardens | `urban_park`, `garden`, `nature_reserve` |
| `forest` | Forested areas | `managed_forest`, `tree_nursery` |
| `cemetery` | Burial grounds | `cemetery` |
| `religious` | Religious sites | `churchyard` |
| `military` | Military installations | `military`, `barracks`, `training_area` |
| `education` | Schools/universities | `school`, `university`, `college` |
| `medical` | Healthcare facilities | `hospital` |
| `transportation` | Transport infrastructure | `railway`, `bus_station` |
| `airport` | Airports | `runway`, `taxiway`, `terminal` |
| `port` | Ports and harbors | `port`, `dock` |
| `dam` | Dams | `dam` |
| `quarry` | Mining/quarrying sites | `quarry`, `mine` |
| `landfill` | Waste disposal sites | `landfill` |
| `brownfield` | Previously developed land | `brownfield` |
| `greenfield` | Undeveloped land designated for development | `greenfield` |

### Land Use vs Land Cover vs Land

Overture's `base` theme contains three types that are sometimes confused:

| Type | Source | What It Represents | Used in V1? |
|------|--------|-------------------|-------------|
| `land_use` | OpenStreetMap (human-mapped) | How humans use the land (zoning: residential, commercial, park) | **Yes** |
| `land_cover` | Satellite imagery (ESA/Copernicus) | Physical surface (trees, grass, water, bare rock) | No — too granular for agent reasoning |
| `land` | OpenStreetMap | Natural terrain features (islands, peninsulas) | No — not useful for site selection |

### Sample Query: Land Use at a Point
```sql
-- Note: ST_Contains operates in coordinate space. No ST_FlipCoordinates needed.
SELECT
    subtype,
    class,
    names."primary" AS names_primary,
    sources[1].dataset AS source
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=base/type=land_use/*')
WHERE bbox.xmin <= 4.9041 AND bbox.xmax >= 4.9041
  AND bbox.ymin <= 52.3676 AND bbox.ymax >= 52.3676
  AND ST_Contains(geometry, ST_Point(4.9041, 52.3676));
```

### Sample Query: Land Use Composition in 1km
```sql
-- Note: Land use has Polygon geometry. Same centroid pattern as buildings.
SELECT
    subtype,
    COUNT(*) AS count
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=base/type=land_use/*')
WHERE bbox.xmin BETWEEN 4.890 AND 4.918
  AND bbox.ymin BETWEEN 52.358 AND 52.377
  AND ST_Distance_Spheroid(
        ST_FlipCoordinates(ST_Centroid(geometry)),
        ST_FlipCoordinates(ST_Point(4.9041, 52.3676))
      ) < 1000
GROUP BY subtype
ORDER BY count DESC;
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
- **Places** (~5 GB): Fast queries, small individual records (Point geometry).
- **Buildings** (~50 GB): Large dataset, polygon geometries. Keep radius small for fast results.
- **Divisions** (~2 GB): Small dataset but large individual geometries (country boundaries are complex polygons). Point-in-polygon checks can be slow for complex boundaries.
- **Transportation** (~46 GB): Very large dataset, LineString geometries. The bbox pre-filter is critical — without it, queries would scan the entire dataset. Urban areas with dense road networks may return hundreds of segments within small radii.
- **Land Use** (~3 GB): Moderate dataset, Polygon/MultiPolygon geometries. Similar performance characteristics to buildings but smaller. Point-in-polygon queries are fast. Radius queries use centroid-based distance (same pattern as buildings).
