"""
Operation handlers for the Buildings theme.
"""

from __future__ import annotations

import logging
from typing import Any

from overture_mcp.config import ServerConfig
from overture_mcp.db import Database
from overture_mcp.queries.buildings import (
    building_composition_query,
    building_count_query,
)
from overture_mcp.response import empty_response, success_response
from overture_mcp.validation import validate_lat, validate_lng, validate_radius

logger = logging.getLogger(__name__)


class BuildingsOperations:
    """Handlers for buildings-themed operations."""

    def __init__(self, db: Database, config: ServerConfig):
        self._db = db
        self._config = config

    async def building_count_in_radius(self, params: dict[str, Any]) -> dict[str, Any]:
        """Count total buildings within a radius of a point."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)

        query_params = {"lat": lat, "lng": lng, "radius_m": radius_m}

        data_source = self._db.resolve_source(
            "building", lat, lng, radius_m, self._config.buildings_path,
        )
        sql, sql_params = building_count_query(
            lat=lat, lng=lng, radius_m=radius_m,
            data_source=data_source,
        )

        rows = await self._db.execute_query(sql, sql_params)
        count = rows[0][0] if rows else 0

        result = {"count": count, "radius_m": radius_m}

        if count == 0:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"Zero buildings found within {radius_m}m. "
                           "This may be an undeveloped area or indicate "
                           "sparse coverage in this region.",
            )

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def building_class_composition(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get the percentage breakdown of building types within a radius."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)

        query_params = {"lat": lat, "lng": lng, "radius_m": radius_m}

        data_source = self._db.resolve_source(
            "building", lat, lng, radius_m, self._config.buildings_path,
        )
        sql, sql_params = building_composition_query(
            lat=lat, lng=lng, radius_m=radius_m,
            data_source=data_source,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"Zero buildings found within {radius_m}m. "
                           "Cannot compute composition for an area with no buildings.",
            )

        # Compute total and percentages
        total = sum(row[1] for row in rows)
        composition = {}
        for row in rows:
            building_class = row[0]
            count = row[1]
            percentage = round((count / total) * 100, 1) if total > 0 else 0.0
            composition[building_class] = {
                "count": count,
                "percentage": percentage,
            }

        result = {
            "total_buildings": total,
            "composition": composition,
            "radius_m": radius_m,
        }

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )
