"""
SQL query builders for the Divisions (Admin Boundaries) theme.

Uses ST_Contains for point-in-polygon checks (not ST_Distance_Spheroid).
ST_Contains operates in coordinate space and does NOT need ST_FlipCoordinates.

Overture division_area subtypes ordered broadest → most specific:
  country, dependency, region, county, localadmin, locality,
  neighborhood, macrohood, microhood.

The `admin_level` column exists in some Overture releases but not all.
We use a CASE expression on `subtype` to derive a stable ordering.
"""

from __future__ import annotations


# Synthetic admin level from subtype (broadest → most specific).
# These align with the OSM admin_level conventions where they exist.
SUBTYPE_LEVEL_CASE = """CASE subtype
        WHEN 'country' THEN 2
        WHEN 'dependency' THEN 3
        WHEN 'region' THEN 4
        WHEN 'county' THEN 6
        WHEN 'localadmin' THEN 7
        WHEN 'locality' THEN 8
        WHEN 'neighborhood' THEN 9
        WHEN 'macrohood' THEN 10
        WHEN 'microhood' THEN 11
        ELSE 99
    END"""


def point_in_boundary_query(
    lat: float,
    lng: float,
    data_source: str,
) -> tuple[str, list]:
    """Build SQL to find which admin boundaries contain a point.

    Uses bbox pre-filter for containment (xmin <= lng <= xmax, ymin <= lat <= ymax)
    followed by exact ST_Contains check. Filters to class='land' to avoid
    duplicate maritime boundaries.

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
        {SUBTYPE_LEVEL_CASE} AS admin_level,
        subtype
    FROM {data_source}
    WHERE bbox.xmin <= ? AND bbox.xmax >= ?
      AND bbox.ymin <= ? AND bbox.ymax >= ?
      AND ST_Contains(geometry, ST_Point(?, ?))
      AND class = 'land'
    ORDER BY admin_level ASC"""

    params = [
        lng, lng,   # bbox containment check for longitude
        lat, lat,   # bbox containment check for latitude
        lng, lat,   # ST_Point for ST_Contains (standard GIS convention)
    ]

    return sql, params
