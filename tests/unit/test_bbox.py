"""Unit tests for bounding box computation."""

import math
import pytest
from overture_mcp.bbox import radius_to_bbox_delta, compute_bbox, METERS_PER_DEGREE_LAT


class TestRadiusToBboxDelta:
    """Tests for radius_to_bbox_delta function."""

    def test_equator(self):
        """At the equator, lat_delta ≈ lng_delta (cos(0) = 1)."""
        lat_delta, lng_delta = radius_to_bbox_delta(0.0, 1000)
        assert abs(lat_delta - lng_delta) < 0.001

    def test_high_latitude(self):
        """At lat=60, lng_delta > lat_delta (cos(60) = 0.5)."""
        lat_delta, lng_delta = radius_to_bbox_delta(60.0, 1000)
        assert lng_delta > lat_delta
        # At lat 60: lng_delta should be roughly 2x lat_delta
        assert abs(lng_delta / lat_delta - 2.0) < 0.1

    def test_500m_equator(self):
        """500m radius → ~0.0045 degree delta at equator."""
        lat_delta, lng_delta = radius_to_bbox_delta(0.0, 500)
        expected = 500 / METERS_PER_DEGREE_LAT
        assert abs(lat_delta - expected) < 0.0001

    def test_50km_equator(self):
        """50km radius → ~0.45 degree delta at equator."""
        lat_delta, lng_delta = radius_to_bbox_delta(0.0, 50000)
        expected = 50000 / METERS_PER_DEGREE_LAT
        assert abs(lat_delta - expected) < 0.001

    def test_near_pole(self):
        """Near pole, lng_delta should be very large (cos→0), no division by zero."""
        lat_delta, lng_delta = radius_to_bbox_delta(89.99, 1000)
        # Should not raise and should be a large value
        assert lng_delta > 10.0  # At near-pole, lng_delta is huge

    def test_exact_pole(self):
        """At exactly 90°, should use the 180° fallback."""
        lat_delta, lng_delta = radius_to_bbox_delta(90.0, 1000)
        assert lng_delta == 180.0

    def test_bbox_always_larger_than_radius(self):
        """Bbox should always fully contain the search circle."""
        for lat in [0, 30, 45, 60, 75]:
            for radius in [100, 500, 1000, 10000]:
                lat_delta, lng_delta = radius_to_bbox_delta(lat, radius)
                # Bbox edge in meters should be >= radius
                bbox_edge_lat_m = lat_delta * METERS_PER_DEGREE_LAT
                bbox_edge_lng_m = lng_delta * METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))
                assert bbox_edge_lat_m >= radius, f"lat bbox too small at lat={lat}, r={radius}"
                assert bbox_edge_lng_m >= radius * 0.99, f"lng bbox too small at lat={lat}, r={radius}"


class TestComputeBbox:
    """Tests for compute_bbox function."""

    def test_returns_four_values(self):
        result = compute_bbox(52.3676, 4.9041, 500)
        assert len(result) == 4

    def test_lat_min_less_than_lat_max(self):
        lat_min, lat_max, lng_min, lng_max = compute_bbox(52.3676, 4.9041, 500)
        assert lat_min < lat_max

    def test_lng_min_less_than_lng_max(self):
        lat_min, lat_max, lng_min, lng_max = compute_bbox(52.3676, 4.9041, 500)
        assert lng_min < lng_max

    def test_center_inside_bbox(self):
        lat_min, lat_max, lng_min, lng_max = compute_bbox(52.3676, 4.9041, 500)
        assert lat_min < 52.3676 < lat_max
        assert lng_min < 4.9041 < lng_max

    def test_larger_radius_larger_bbox(self):
        small = compute_bbox(52.3676, 4.9041, 500)
        large = compute_bbox(52.3676, 4.9041, 5000)
        # Larger radius should have wider bbox
        assert (large[1] - large[0]) > (small[1] - small[0])
        assert (large[3] - large[2]) > (small[3] - small[2])
