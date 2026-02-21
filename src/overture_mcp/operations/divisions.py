"""
Operation handlers for the Divisions (Admin Boundaries) theme.
"""

from __future__ import annotations

import logging
from typing import Any

from overture_mcp.config import ServerConfig
from overture_mcp.db import Database
from overture_mcp.queries.divisions import point_in_boundary_query
from overture_mcp.response import empty_response, success_response
from overture_mcp.validation import validate_lat, validate_lng

logger = logging.getLogger(__name__)


class DivisionsOperations:
    """Handlers for divisions-themed operations."""

    def __init__(self, db: Database, config: ServerConfig):
        self._db = db
        self._config = config

    async def point_in_admin_boundary(self, params: dict[str, Any]) -> dict[str, Any]:
        """Determine what administrative boundaries contain a given point."""
        lat = validate_lat(params.get("lat"))
        lng = validate_lng(params.get("lng"))

        query_params = {"lat": lat, "lng": lng}

        data_source = self._db.resolve_source_point(
            "division_area", lat, lng, self._config.divisions_path,
        )
        sql, sql_params = point_in_boundary_query(
            lat=lat, lng=lng,
            data_source=data_source,
        )

        rows = await self._db.execute_query(sql, sql_params)

        if not rows:
            return empty_response(
                query_params=query_params,
                data_version=self._config.data_version,
                suggestion="No administrative boundaries found for this point. "
                           "It may be in international waters or an area "
                           "with limited coverage.",
            )

        # Build admin level hierarchy
        admin_levels = []
        locality = None
        region = None
        country = None

        for row in rows:
            name = row[0]
            admin_level = row[1]
            subtype = row[2]

            admin_levels.append({
                "level": admin_level,
                "name": name,
                "type": subtype,
            })

            # Extract convenience fields
            if subtype == "country" or admin_level == 2:
                country = name
            elif subtype == "region" or admin_level == 4:
                region = name
            elif subtype == "locality" or admin_level == 8:
                locality = name

        result = {
            "locality": locality,
            "region": region,
            "country": country,
            "admin_levels": admin_levels,
        }

        return success_response(
            results=[result],
            query_params=query_params,
            data_version=self._config.data_version,
        )
