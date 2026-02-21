"""
SQL query builders for the Transportation theme.

All functions return (sql, params) tuples with ? placeholders.
No string interpolation of user-provided values.

Transportation segments are LineString geometries. Distance is calculated
using ST_PointOnSurface(geometry) to get a point guaranteed to lie on the
line, then ST_FlipCoordinates for ST_Distance_Spheroid.

All queries filter to subtype='road' (excludes rail and water segments).
"""

from __future__ import annotations

from overture_mcp.bbox import compute_bbox


def road_count_by_class_query(
    lat: float,
    lng: float,
    radius_m: int,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to count road segments by class within a radius.

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
        COALESCE(class, 'unknown') AS road_class,
        COUNT(*) AS count
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND subtype = 'road'
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_PointOnSurface(geometry)),
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


def nearest_road_of_class_query(
    lat: float,
    lng: float,
    road_class: str,
    data_source: str,
    max_radius_m: int = 5000,
    include_geometry: bool = False,
) -> tuple[str, list]:
    """Build SQL to find the closest road segment of a given class.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        road_class: Road class (e.g., 'residential', 'primary').
        data_source: Parquet data source path or view name.
        max_radius_m: Maximum search radius in meters.
        include_geometry: Whether to include WKT geometry.

    Returns:
        Tuple of (sql_string, params_list).
    """
    lat_min, lat_max, lng_min, lng_max = compute_bbox(lat, lng, max_radius_m)

    geometry_col = ""
    if include_geometry:
        geometry_col = ",\n        ST_AsText(geometry) AS geometry"

    sql = f"""SELECT
        names."primary" AS name,
        class AS road_class,
        road_surface[1].value AS road_surface,
        CAST(ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_PointOnSurface(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
        ) AS INTEGER) AS distance_m,
        ST_Y(ST_PointOnSurface(geometry)) AS lat,
        ST_X(ST_PointOnSurface(geometry)) AS lng,
        COALESCE(list_contains(
            flatten(list_transform(road_flags, x -> x.values)),
            'is_bridge'
        ), false) AS is_bridge,
        COALESCE(list_contains(
            flatten(list_transform(road_flags, x -> x.values)),
            'is_tunnel'
        ), false) AS is_tunnel,
        COALESCE(list_contains(
            flatten(list_transform(road_flags, x -> x.values)),
            'is_link'
        ), false) AS is_link{geometry_col}
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND subtype = 'road'
      AND class = ?
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_PointOnSurface(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?
    ORDER BY distance_m ASC
    LIMIT 1"""

    params = [
        lng, lat,                   # ST_Point for distance calc (SELECT)
        lng_min, lng_max,           # bbox.xmin range
        lat_min, lat_max,           # bbox.ymin range
        road_class,                 # class filter
        lng, lat,                   # ST_Point for distance filter (WHERE)
        max_radius_m,               # radius threshold
    ]

    return sql, params


def road_surface_composition_query(
    lat: float,
    lng: float,
    radius_m: int,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to get road surface composition within a radius.

    Groups road segments by surface type, mapping NULL to 'unknown'.

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
        COALESCE(road_surface[1].value, 'unknown') AS surface_type,
        COUNT(*) AS count
    FROM {data_source}
    WHERE bbox.xmin BETWEEN ? AND ?
      AND bbox.ymin BETWEEN ? AND ?
      AND subtype = 'road'
      AND ST_Distance_Spheroid(
            ST_FlipCoordinates(ST_PointOnSurface(geometry)),
            ST_FlipCoordinates(ST_Point(?, ?))
          ) < ?
    GROUP BY COALESCE(road_surface[1].value, 'unknown')
    ORDER BY count DESC"""

    params = [
        lng_min, lng_max,
        lat_min, lat_max,
        lng, lat,
        radius_m,
    ]

    return sql, params
