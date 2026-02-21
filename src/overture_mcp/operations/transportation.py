"""
Operation handlers for the Transportation theme.
"""

from __future__ import annotations

import logging
from typing import Any

from overture_mcp.config import ServerConfig
from overture_mcp.db import Database
from overture_mcp.queries.transportation import (
    nearest_road_of_class_query,
    road_count_by_class_query,
    road_surface_composition_query,
)
from overture_mcp.response import empty_response, success_response
from overture_mcp.validation import (
    validate_include_geometry,
    validate_lat,
    validate_lng,
    validate_radius,
    validate_road_class,
)

logger = logging.getLogger(__name__)


class TransportationOperations:
    """Handlers for transportation-themed operations."""

    def __init__(self, db: Database, config: ServerConfig):
        self._db = db
        self._config = config

    async def road_count_by_class(self, params: dict[str, Any]) -> dict[str, Any]:
        """Count road segments grouped by road class within a radius."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)

        query_params = {"lat": lat, "lng": lng, "radius_m": radius_m}

        data_source = self._db.resolve_source(
            "segment", lat, lng, radius_m, self._config.transportation_path,
        )
        sql, sql_params = road_count_by_class_query(
            lat=lat, lng=lng, radius_m=radius_m,
            data_source=data_source,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"Zero road segments found within {radius_m}m. "
                           "This may be an undeveloped area or an area "
                           "with limited road mapping.",
            )

        # Compute total and class breakdown
        total = sum(row[1] for row in rows)
        by_class = {}
        for row in rows:
            road_class = row[0]
            count = row[1]
            percentage = round((count / total) * 100, 1) if total > 0 else 0.0
            by_class[road_class] = {
                "count": count,
                "percentage": percentage,
            }

        result = {
            "total_segments": total,
            "by_class": by_class,
            "radius_m": radius_m,
        }

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def nearest_road_of_class(self, params: dict[str, Any]) -> dict[str, Any]:
        """Find the single closest road segment of a given class."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        road_class = validate_road_class(params.get("road_class"))
        max_radius_m = validate_radius(
            params.get("max_radius_m", 5000), self._config.max_radius_m
        )
        include_geometry = validate_include_geometry(params.get("include_geometry"))

        query_params = {
            "lat": lat, "lng": lng,
            "road_class": road_class, "max_radius_m": max_radius_m,
        }

        data_source = self._db.resolve_source(
            "segment", lat, lng, max_radius_m, self._config.transportation_path,
        )
        sql, sql_params = nearest_road_of_class_query(
            lat=lat, lng=lng, road_class=road_class,
            data_source=data_source,
            max_radius_m=max_radius_m,
            include_geometry=include_geometry,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"No {road_class} road found within {max_radius_m}m. "
                           "Try increasing max_radius_m or use a more common road class.",
            )

        row = rows[0]
        result = {
            "name": row[0],
            "road_class": row[1],
            "road_surface": row[2],
            "distance_m": row[3],
            "lat": round(row[4], 7),
            "lng": round(row[5], 7),
            "is_bridge": row[6],
            "is_tunnel": row[7],
            "is_link": row[8],
        }

        if include_geometry and len(row) > 9:
            geom = row[9]
            if geom and len(str(geom)) <= self._config.geometry_wkt_cap:
                result["geometry"] = str(geom)
            elif geom:
                result["geometry_note"] = (
                    "Geometry too large (>10,000 chars). Omitted to save tokens."
                )

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def road_surface_composition(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get the percentage breakdown of road surface types within a radius."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)

        query_params = {"lat": lat, "lng": lng, "radius_m": radius_m}

        data_source = self._db.resolve_source(
            "segment", lat, lng, radius_m, self._config.transportation_path,
        )
        sql, sql_params = road_surface_composition_query(
            lat=lat, lng=lng, radius_m=radius_m,
            data_source=data_source,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"Zero road segments found within {radius_m}m. "
                           "Cannot compute surface composition for an area with no roads.",
            )

        # Compute total and surface breakdown
        total = sum(row[1] for row in rows)
        composition = {}
        for row in rows:
            surface_type = row[0]
            count = row[1]
            percentage = round((count / total) * 100, 1) if total > 0 else 0.0
            composition[surface_type] = {
                "count": count,
                "percentage": percentage,
            }

        result = {
            "total_segments": total,
            "composition": composition,
            "radius_m": radius_m,
        }

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )
