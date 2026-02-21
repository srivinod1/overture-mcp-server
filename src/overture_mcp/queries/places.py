"""
SQL query builders for the Places theme.

All functions return (sql, params) tuples with ? placeholders.
No string interpolation of user-provided values.
ST_FlipCoordinates is used on all geometry arguments to ST_Distance_Spheroid
because DuckDB expects (lat, lng) internally but Overture stores (lng, lat).
"""

from __future__ import annotations

from overture_mcp.bbox import compute_bbox


def places_in_radius_query(
    lat: float,
    lng: float,
    radius_m: int,
    category: str,
    data_source: str,
    limit: int = 20,
    include_geometry: bool = False,
) -> tuple[str, list]:
    """Build SQL to find places matching a category within a radius.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        radius_m: Search radius in meters.
        category: Overture category ID.
        data_source: Parquet data source path or view name.
        limit: Maximum results to return.
        include_geometry: Whether to include WKT geometry in results.

    Returns:
        Tuple of (sql_string, params_list).
    """
    lat_min, lat_max, lng_min, lng_max = compute_bbox(lat, lng, radius_m)

    geometry_col = ""
    if include_geometry:
        geometry_col = ",\n        ST_AsText(geometry) AS geometry"

    sql = f"""SELECT
        names."primary" AS name,
        categories."primary" AS category,
        ST_Y(geometry) AS lat,
        ST_X(geometry) AS lng,
        CAST(ST_Distance_Spheroid(
            ST_FlipCoordinates(geometry),
            ST_FlipCoordinates(ST_Point(?, ?))
        ) AS INTEGER) AS distance_m{geometry_col}
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(geometry),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?
      AND categories."primary" = ?
    ORDER BY distance_m ASC
    LIMIT ?"""

    params = [
        lng, lat,                   # ST_Point for distance calc (SELECT)
        lng_min, lng_max,           # bbox.xmin range
        lat_min, lat_max,           # bbox.ymin range
        lng, lat,                   # ST_Point for distance filter (WHERE)
        radius_m,                   # radius threshold
        category,                   # category filter
        limit,                      # result limit
    ]

    return sql, params


def nearest_place_query(
    lat: float,
    lng: float,
    category: str,
    data_source: str,
    max_radius_m: int = 5000,
    include_geometry: bool = False,
) -> tuple[str, list]:
    """Build SQL to find the single closest place of a given type.

    Same as places_in_radius but with LIMIT 1.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        category: Overture category ID.
        data_source: Parquet data source path or view name.
        max_radius_m: Maximum search radius in meters.
        include_geometry: Whether to include WKT geometry.

    Returns:
        Tuple of (sql_string, params_list).
    """
    return places_in_radius_query(
        lat=lat,
        lng=lng,
        radius_m=max_radius_m,
        category=category,
        data_source=data_source,
        limit=1,
        include_geometry=include_geometry,
    )


def count_places_query(
    lat: float,
    lng: float,
    radius_m: int,
    category: str,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to count places of a category in an area.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        radius_m: Search radius in meters.
        category: Overture category ID.
        data_source: Parquet data source path or view name.

    Returns:
        Tuple of (sql_string, params_list).
    """
    lat_min, lat_max, lng_min, lng_max = compute_bbox(lat, lng, radius_m)

    sql = f"""SELECT COUNT(*) AS count
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(geometry),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?
      AND categories."primary" = ?"""

    params = [
        lng_min, lng_max,
        lat_min, lat_max,
        lng, lat,
        radius_m,
        category,
    ]

    return sql, params
