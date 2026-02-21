"""
SQL query builders for the Divisions (Admin Boundaries) theme.

Uses ST_Contains for point-in-polygon checks (not ST_Distance_Spheroid).
ST_Contains operates in coordinate space and does NOT need ST_FlipCoordinates.
"""

from __future__ import annotations


def point_in_boundary_query(
    lat: float,
    lng: float,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to find which admin boundaries contain a point.

    Uses bbox pre-filter for containment (xmin <= lng <= xmax, ymin <= lat <= ymax)
    followed by exact ST_Contains check.

    Note: ST_Contains does NOT need ST_FlipCoordinates because it operates in
    coordinate space (checking if a point's coordinates fall within a polygon's
    coordinate ring), not on an ellipsoid surface.

    Args:
        lat: Latitude of the point.
        lng: Longitude of the point.
        data_source: Parquet data source path or view name.

    Returns:
        Tuple of (sql_string, params_list).
    """
    sql = f"""SELECT
        names."primary" AS name,
        admin_level,
        subtype
    FROM {data_source}
    WHERE bbox.xmin <= ? AND bbox.xmax >= ?
      AND bbox.ymin <= ? AND bbox.ymax >= ?
      AND ST_Contains(geometry, ST_Point(?, ?))
    ORDER BY admin_level ASC"""

    params = [
        lng, lng,   # bbox containment check for longitude
        lat, lat,   # bbox containment check for latitude
        lng, lat,   # ST_Point for ST_Contains (standard GIS convention)
    ]

    return sql, params
