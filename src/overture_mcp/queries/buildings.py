"""
SQL query builders for the Buildings theme.

All functions return (sql, params) tuples with ? placeholders.
No category filter — buildings are queried by location only.

Buildings have polygon geometries (footprints), not points. DuckDB's
ST_FlipCoordinates cannot operate on polygons directly, so we use
ST_Centroid(geometry) to get the center point first, then flip for
ST_Distance_Spheroid.  Pattern: ST_FlipCoordinates(ST_Centroid(geometry)).
"""

from __future__ import annotations

from overture_mcp.bbox import compute_bbox


def building_count_query(
    lat: float,
    lng: float,
    radius_m: int,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to count buildings within a radius.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        radius_m: Search radius in meters.
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
            ST_FlipCoordinates(ST_Centroid(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?"""

    params = [
        lng_min, lng_max,
        lat_min, lat_max,
        lng, lat,
        radius_m,
    ]

    return sql, params


def building_composition_query(
    lat: float,
    lng: float,
    radius_m: int,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to get building class composition within a radius.

    Groups buildings by class, mapping NULL to 'unknown'.

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
        COALESCE(class, 'unknown') AS building_class,
        COUNT(*) AS count
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_Centroid(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?
    GROUP BY COALESCE(class, 'unknown')
    ORDER BY count DESC"""

    params = [
        lng_min, lng_max,
        lat_min, lat_max,
        lng, lat,
        radius_m,
    ]

    return sql, params
