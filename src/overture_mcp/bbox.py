"""
Bounding box computation for spatial pre-filtering.

Converts a radius in meters to approximate latitude/longitude deltas
for use as bbox pre-filters in DuckDB queries. The bbox is intentionally
generous (larger than the actual radius) to avoid clipping results.
The precise ST_Distance_Spheroid filter handles exact distance checking.
"""

from __future__ import annotations

import math


# Earth circumference constants
METERS_PER_DEGREE_LAT = 111_320  # ~111.32 km per degree of latitude


def radius_to_bbox_delta(lat: float, radius_m: float) -> tuple[float, float]:
    """Convert radius in meters to approximate lat/lng deltas for bbox pre-filter.

    The deltas are slightly generous to ensure the bbox fully contains
    the search circle. The exact ST_Distance_Spheroid filter handles
    precise distance checking.

    Args:
        lat: Latitude of the center point (for longitude scaling).
        radius_m: Search radius in meters.

    Returns:
        Tuple of (lat_delta, lng_delta) in degrees.
    """
    lat_delta = radius_m / METERS_PER_DEGREE_LAT

    # Scale longitude by cos(latitude) to account for meridian convergence.
    # At the poles, cos(lat) approaches 0, so we clamp to prevent division
    # by near-zero values and use a large delta instead.
    cos_lat = math.cos(math.radians(lat))
    if cos_lat < 0.01:
        # Near the poles: use a very large longitude delta (effectively no filter)
        lng_delta = 180.0
    else:
        lng_delta = radius_m / (METERS_PER_DEGREE_LAT * cos_lat)

    return lat_delta, lng_delta


def compute_bbox(
    lat: float, lng: float, radius_m: float
) -> tuple[float, float, float, float]:
    """Compute bounding box coordinates for a radius search.

    Args:
        lat: Center latitude.
        lng: Center longitude.
        radius_m: Search radius in meters.

    Returns:
        Tuple of (lat_min, lat_max, lng_min, lng_max).
    """
    lat_delta, lng_delta = radius_to_bbox_delta(lat, radius_m)

    lat_min = lat - lat_delta
    lat_max = lat + lat_delta
    lng_min = lng - lng_delta
    lng_max = lng + lng_delta

    return lat_min, lat_max, lng_min, lng_max
