"""
STAC index for targeted S3 file resolution.

Instead of scanning all parquet files in a theme (which requires fetching
metadata from potentially hundreds of files), we use Overture's STAC
GeoParquet index to identify which specific files contain data for a
given bounding box. This drops cold-start latency from ~50s to ~5s for
large themes like buildings (236 files -> 1-2 files).

The STAC index is a lightweight parquet file (~100-500KB) hosted at
https://stac.overturemaps.org/{version}/collections.parquet that contains
one row per data file with its spatial bounding box and S3 path.
"""

from __future__ import annotations

import logging
from typing import Any

from overture_mcp.bbox import compute_bbox

logger = logging.getLogger(__name__)

STAC_BASE_URL = "https://stac.overturemaps.org"

# Maps our config property names to STAC collection names
THEME_TO_COLLECTION = {
    "places": "place",
    "buildings": "building",
    "divisions": "division_area",
    "transportation": "segment",
    "land_use": "land_use",
}


class StacIndex:
    """Cached STAC index for resolving S3 file paths by bounding box.

    Loaded once at server startup. Each resolve() call filters the cached
    index to find which S3 files overlap the query's bounding box, then
    returns a read_parquet([...]) SQL fragment targeting only those files.
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self, conn: Any, data_version: str) -> None:
        """Download and cache the STAC index.

        Args:
            conn: DuckDB connection (must have httpfs loaded).
            data_version: Overture release version (e.g., "2026-01-21.0").
        """
        stac_url = f"{STAC_BASE_URL}/{data_version}/collections.parquet"
        logger.info("Loading STAC index from %s...", stac_url)

        try:
            rows = conn.execute(f"""
                SELECT
                    collection,
                    bbox.xmin AS xmin,
                    bbox.ymin AS ymin,
                    bbox.xmax AS xmax,
                    bbox.ymax AS ymax,
                    assets.aws.alternate.s3.href AS s3_path
                FROM read_parquet('{stac_url}')
            """).fetchall()

            self._entries = [
                {
                    "collection": row[0],
                    "xmin": row[1],
                    "ymin": row[2],
                    "xmax": row[3],
                    "ymax": row[4],
                    "s3_path": row[5],
                }
                for row in rows
                if row[5]  # skip entries without S3 path
            ]
            self._loaded = True
            logger.info(
                "STAC index loaded: %d entries across %d collections",
                len(self._entries),
                len(set(e["collection"] for e in self._entries)),
            )
        except Exception as e:
            logger.warning("Failed to load STAC index: %s. Will use glob fallback.", e)
            self._loaded = False

    def resolve(
        self,
        collection: str,
        lat: float,
        lng: float,
        radius_m: int,
    ) -> str | None:
        """Find S3 files that overlap the query bounding box.

        Args:
            collection: STAC collection name (e.g., "place", "building").
            lat: Center latitude.
            lng: Center longitude.
            radius_m: Search radius in meters.

        Returns:
            A read_parquet([...]) SQL fragment with only the matching files,
            or None if STAC is not loaded (caller should use glob fallback).
        """
        if not self._loaded:
            return None

        lat_min, lat_max, lng_min, lng_max = compute_bbox(lat, lng, radius_m)

        # Find files whose bounding box intersects the query bbox
        matching = [
            e["s3_path"]
            for e in self._entries
            if e["collection"] == collection
            and e["xmin"] < lng_max  # file extends past query's west edge
            and e["xmax"] > lng_min  # file extends past query's east edge
            and e["ymin"] < lat_max  # file extends past query's south edge
            and e["ymax"] > lat_min  # file extends past query's north edge
        ]

        if not matching:
            # No files found — may be ocean/empty area. Return None to
            # fall back to glob (which will also return 0 results, but
            # won't error on an empty file list).
            return None

        # Build read_parquet SQL with explicit file list
        file_list = ", ".join(f"'{path}'" for path in matching)
        return f"read_parquet([{file_list}])"

    def resolve_for_point(
        self,
        collection: str,
        lat: float,
        lng: float,
    ) -> str | None:
        """Find S3 files that contain a specific point.

        Used for point-in-polygon operations (divisions, land_use_at_point)
        that don't have a radius.

        Args:
            collection: STAC collection name.
            lat: Point latitude.
            lng: Point longitude.

        Returns:
            A read_parquet([...]) SQL fragment, or None for glob fallback.
        """
        if not self._loaded:
            return None

        matching = [
            e["s3_path"]
            for e in self._entries
            if e["collection"] == collection
            and e["xmin"] <= lng <= e["xmax"]
            and e["ymin"] <= lat <= e["ymax"]
        ]

        if not matching:
            return None

        file_list = ", ".join(f"'{path}'" for path in matching)
        return f"read_parquet([{file_list}])"
