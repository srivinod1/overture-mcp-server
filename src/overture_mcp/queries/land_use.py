"""
SQL query builders for the Land Use theme.

All functions return (sql, params) tuples with ? placeholders.
No string interpolation of user-provided values.

Land use parcels have Polygon/MultiPolygon geometries.
- Point-in-polygon queries use ST_Contains(geometry, ST_Point(lng, lat)).
  No ST_FlipCoordinates needed (ST_Contains operates in coordinate space).
- Radius-based queries use the centroid pattern:
  ST_FlipCoordinates(ST_Centroid(geometry)) for ST_Distance_Spheroid.
  Same approach as buildings.

Data source: theme=base/type=land_use (under the base theme, not its own theme).
"""

from __future__ import annotations

from overture_mcp.bbox import compute_bbox


def land_use_at_point_query(
    lat: float,
    lng: float,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to find land use designation(s) at a specific point.

    A single point may be covered by multiple overlapping land use polygons.
    Returns all matches.

    Args:
        lat: Point latitude.
        lng: Point longitude.
        data_source: Parquet data source path or view name.

    Returns:
        Tuple of (sql_string, params_list).
    """
    sql = f"""SELECT
        subtype,
        class,
        names."primary" AS names_primary,
        sources[1].dataset AS source
    FROM {data_source}
    WHERE bbox.xmin <= ? AND bbox.xmax >= ?
      AND bbox.ymin <= ? AND bbox.ymax >= ?
      AND ST_Contains(geometry, ST_Point(?, ?))"""

    params = [
        lng, lng,     # bbox.xmin <= lng AND bbox.xmax >= lng
        lat, lat,     # bbox.ymin <= lat AND bbox.ymax >= lat
        lng, lat,     # ST_Point(lng, lat) for ST_Contains
    ]

    return sql, params


def land_use_composition_query(
    lat: float,
    lng: float,
    radius_m: int,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to get land use composition within a radius.

    Groups by subtype for a manageable number of categories.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        radius_m: Search radius in meters.
        data_source: Parquet data source path or view name.

    Returns:
        Tuple of (sql_string, params_list).
    """
    lat_min, lat_max, lng_min, lng_max = compute_bbox(lat, lng, radius_m)

    sql = f"""SELECT
        subtype,
        COUNT(*) AS count
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_Centroid(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?
    GROUP BY subtype
    ORDER BY count DESC"""

    params = [
        lng_min, lng_max,
        lat_min, lat_max,
        lng, lat,
        radius_m,
    ]

    return sql, params


def land_use_search_query(
    lat: float,
    lng: float,
    radius_m: int,
    subtype: str,
    data_source: str,
    limit: int = 20,
    include_geometry: bool = False,
) -> tuple[str, list]:
    """Build SQL to find land use parcels of a specific subtype within a radius.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        radius_m: Search radius in meters.
        subtype: Land use subtype (e.g., 'residential', 'park').
        data_source: Parquet data source path or view name.
        limit: Maximum results to return.
        include_geometry: Whether to include WKT geometry.

    Returns:
        Tuple of (sql_string, params_list).
    """
    lat_min, lat_max, lng_min, lng_max = compute_bbox(lat, lng, radius_m)

    geometry_col = ""
    if include_geometry:
        geometry_col = ",\n        ST_AsText(geometry) AS geometry"

    sql = f"""SELECT
        subtype,
        class,
        names."primary" AS names_primary,
        ST_Y(ST_Centroid(geometry)) AS lat,
        ST_X(ST_Centroid(geometry)) AS lng,
        CAST(ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_Centroid(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
        ) AS INTEGER) AS distance_m{geometry_col}
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND subtype = ?
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_Centroid(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?
    ORDER BY distance_m ASC
    LIMIT ?"""

    params = [
        lng, lat,                   # ST_Point for distance calc (SELECT)
        lng_min, lng_max,           # bbox.xmin range
        lat_min, lat_max,           # bbox.ymin range
        subtype,                    # subtype filter
        lng, lat,                   # ST_Point for distance filter (WHERE)
        radius_m,                   # radius threshold
        limit,                      # result limit
    ]

    return sql, params
