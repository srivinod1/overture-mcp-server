"""
Operation handlers for the Land Use theme.
"""

from __future__ import annotations

import logging
from typing import Any

from overture_mcp.config import ServerConfig
from overture_mcp.db import Database
from overture_mcp.queries.land_use import (
    land_use_at_point_query,
    land_use_composition_query,
    land_use_search_query,
)
from overture_mcp.response import empty_response, success_response
from overture_mcp.validation import (
    validate_include_geometry,
    validate_land_use_subtype,
    validate_lat,
    validate_limit,
    validate_lng,
    validate_radius,
)

logger = logging.getLogger(__name__)


class LandUseOperations:
    """Handlers for land-use-themed operations."""

    def __init__(self, db: Database, config: ServerConfig):
        self._db = db
        self._config = config

    async def land_use_at_point(self, params: dict[str, Any]) -> dict[str, Any]:
        """Determine the land use designation at a specific point."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))

        query_params = {"lat": lat, "lng": lng}

        data_source = self._db.resolve_source_point(
            "land_use", lat, lng, self._config.land_use_path,
        )
        sql, sql_params = land_use_at_point_query(
            lat=lat, lng=lng,
            data_source=data_source,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion="No land use designation found for this point. "
                           "The area may lack land use mapping coverage, "
                           "or the point may be in water/unmapped territory.",
            )

        results = []
        for row in rows:
            results.append({
                "subtype": row[0],
                "class": row[1],
                "names_primary": row[2],
                "source": row[3],
            })

        return success_response(
            results=results,
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def land_use_composition(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get the percentage breakdown of land use types within a radius."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)

        query_params = {"lat": lat, "lng": lng, "radius_m": radius_m}

        data_source = self._db.resolve_source(
            "land_use", lat, lng, radius_m, self._config.land_use_path,
        )
        sql, sql_params = land_use_composition_query(
            lat=lat, lng=lng, radius_m=radius_m,
            data_source=data_source,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"Zero land use parcels found within {radius_m}m. "
                           "This area may lack land use mapping coverage. "
                           "Try increasing radius.",
            )

        # Compute total and subtype breakdown
        total = sum(row[1] for row in rows)
        composition = {}
        for row in rows:
            subtype = row[0]
            count = row[1]
            percentage = round((count / total) * 100, 1) if total > 0 else 0.0
            composition[subtype] = {
                "count": count,
                "percentage": percentage,
            }

        result = {
            "total_parcels": total,
            "composition": composition,
            "radius_m": radius_m,
        }

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def land_use_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Find land use parcels of a specific subtype within a radius."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)
        subtype = validate_land_use_subtype(params.get("subtype"))
        limit = validate_limit(params.get("limit"), self._config.max_results)
        include_geometry = validate_include_geometry(params.get("include_geometry"))

        query_params = {
            "lat": lat, "lng": lng,
            "radius_m": radius_m, "subtype": subtype,
        }

        data_source = self._db.resolve_source(
            "land_use", lat, lng, radius_m, self._config.land_use_path,
        )
        sql, sql_params = land_use_search_query(
            lat=lat, lng=lng, radius_m=radius_m,
            subtype=subtype,
            data_source=data_source,
            limit=limit,
            include_geometry=include_geometry,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"No {subtype} land use found within {radius_m}m. "
                           "Try increasing radius or use land_use_composition "
                           "to see what land use types exist in this area.",
            )

        results = []
        for row in rows:
            result = {
                "subtype": row[0],
                "class": row[1],
                "names_primary": row[2],
                "lat": round(row[3], 7),
                "lng": round(row[4], 7),
                "distance_m": row[5],
            }

            if include_geometry and len(row) > 6:
                geom = row[6]
                if geom and len(str(geom)) <= self._config.geometry_wkt_cap:
                    result["geometry"] = str(geom)
                elif geom:
                    result["geometry_note"] = (
                        "Geometry too large (>10,000 chars). Omitted to save tokens."
                    )

            results.append(result)

        return success_response(
            results=results,
            query_params=query_params,
            data_version=self._config.data_version,
        )
