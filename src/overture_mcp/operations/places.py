"""
Operation handlers for the Places theme.

Each handler:
1. Validates parameters
2. Builds the SQL query
3. Executes via the database layer
4. Formats the response envelope
"""

from __future__ import annotations

import json
import logging
from typing import Any

from overture_mcp.config import ServerConfig
from overture_mcp.db import Database
from overture_mcp.queries.places import (
    count_places_query,
    nearest_place_query,
    places_in_radius_query,
)
from overture_mcp.response import empty_response, success_response
from overture_mcp.validation import (
    validate_category,
    validate_include_geometry,
    validate_lat,
    validate_limit,
    validate_lng,
    validate_query,
    validate_radius,
)

logger = logging.getLogger(__name__)


class PlacesOperations:
    """Handlers for places-themed operations."""

    def __init__(self, db: Database, config: ServerConfig, categories: list[dict]):
        self._db = db
        self._config = config
        self._categories = categories
        self._category_names = {c["category"] for c in categories}

    async def get_place_categories(self, params: dict[str, Any]) -> dict[str, Any]:
        """Search and browse the Overture Maps place category taxonomy.

        No S3 query — reads from in-memory cached taxonomy.
        """
        query = validate_query(params.get("query"))
        query_params = {"query": query}

        if query is None:
            # Return top-level categories (all of them, up to 50)
            results = self._categories[:50]
        else:
            # Case-insensitive substring match
            query_lower = query.lower()
            results = [
                c for c in self._categories
                if query_lower in c["category"].lower()
                or query_lower in c.get("description", "").lower()
            ][:50]

        return success_response(
            results=results,
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def places_in_radius(self, params: dict[str, Any]) -> dict[str, Any]:
        """Find all places matching a category within a radius of a point."""
        # Validate
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)
        category = validate_category(params.get("category"), self._category_names)
        limit = validate_limit(params.get("limit"), self._config.max_results)
        include_geometry = validate_include_geometry(params.get("include_geometry"))

        query_params = {
            "lat": lat, "lng": lng, "radius_m": radius_m,
            "category": category, "limit": limit,
        }

        # Build and execute query
        sql, sql_params = places_in_radius_query(
            lat=lat, lng=lng, radius_m=radius_m, category=category,
            data_source=self._config.places_path, limit=limit,
            include_geometry=include_geometry,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"No {category} found within {radius_m}m. "
                           "Try increasing radius or check category with get_place_categories.",
            )

        # Format results
        results = []
        for row in rows:
            result: dict[str, Any] = {
                "name": row[0],
                "category": row[1],
                "lat": row[2],
                "lng": row[3],
                "distance_m": row[4],
            }
            if include_geometry and len(row) > 5:
                geom_wkt = row[5]
                if geom_wkt and len(geom_wkt) > self._config.geometry_wkt_cap:
                    result["geometry_note"] = (
                        f"Geometry too large (>{self._config.geometry_wkt_cap} chars). "
                        "Omitted to save tokens."
                    )
                else:
                    result["geometry"] = geom_wkt
            results.append(result)

        return success_response(
            results=results,
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def nearest_place_of_type(self, params: dict[str, Any]) -> dict[str, Any]:
        """Find the single closest place of a given type to a point."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        category = validate_category(params.get("category"), self._category_names)
        max_radius_m = validate_radius(
            params.get("max_radius_m", 5000), self._config.max_radius_m
        )
        include_geometry = validate_include_geometry(params.get("include_geometry"))

        query_params = {
            "lat": lat, "lng": lng, "category": category,
            "max_radius_m": max_radius_m,
        }

        sql, sql_params = nearest_place_query(
            lat=lat, lng=lng, category=category,
            data_source=self._config.places_path,
            max_radius_m=max_radius_m, include_geometry=include_geometry,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"No {category} found within {max_radius_m}m. "
                           "Try increasing max_radius_m.",
            )

        row = rows[0]
        result: dict[str, Any] = {
            "name": row[0],
            "category": row[1],
            "lat": row[2],
            "lng": row[3],
            "distance_m": row[4],
        }
        if include_geometry and len(row) > 5:
            geom_wkt = row[5]
            if geom_wkt and len(geom_wkt) > self._config.geometry_wkt_cap:
                result["geometry_note"] = (
                    f"Geometry too large (>{self._config.geometry_wkt_cap} chars). "
                    "Omitted to save tokens."
                )
            else:
                result["geometry"] = geom_wkt

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )

    async def count_places_by_type_in_radius(self, params: dict[str, Any]) -> dict[str, Any]:
        """Count how many places of a category exist within a radius."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))
        radius_m = validate_radius(params.get("radius_m"), self._config.max_radius_m)
        category = validate_category(params.get("category"), self._category_names)

        query_params = {
            "lat": lat, "lng": lng, "radius_m": radius_m, "category": category,
        }

        sql, sql_params = count_places_query(
            lat=lat, lng=lng, radius_m=radius_m, category=category,
            data_source=self._config.places_path,
        )

        rows = await self._db.execute_query(sql, sql_params)
        count = rows[0][0] if rows else 0

        result = {
            "count": count,
            "category": category,
            "radius_m": radius_m,
        }

        if count == 0:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion=f"Zero {category} found within {radius_m}m. "
                           "This may indicate sparse coverage in this region, "
                           "or try a larger radius.",
            )

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )
