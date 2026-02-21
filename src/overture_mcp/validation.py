"""
Parameter validation for all operations.

Validates user-provided parameters before they reach the query layer.
Type validation prevents non-numeric values from reaching SQL.
Range validation prevents unreasonable queries (50km+ radius, 100+ results).
Category validation ensures only known taxonomy values reach SQL (defense in depth).
"""

from __future__ import annotations

import math
from typing import Any

from overture_mcp.config import ServerConfig


class ValidationError(Exception):
    """Raised when a parameter fails validation."""

    def __init__(self, message: str, param_name: str | None = None):
        self.message = message
        self.param_name = param_name
        super().__init__(message)


def validate_lat(value: Any) -> float:
    """Validate and return latitude value.

    Args:
        value: Latitude value (must be numeric, -90 to 90).

    Returns:
        Validated float latitude.

    Raises:
        ValidationError: If value is invalid.
    """
    try:
        lat = float(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"lat must be a number. Received: {value!r}",
            param_name="lat",
        )

    if math.isnan(lat) or math.isinf(lat):
        raise ValidationError(
            f"lat must be a finite number. Received: {value!r}",
            param_name="lat",
        )

    if not (-90 <= lat <= 90):
        raise ValidationError(
            f"lat must be between -90 and 90. Received: {lat}",
            param_name="lat",
        )

    return lat


def validate_lng(value: Any) -> float:
    """Validate and return longitude value.

    Args:
        value: Longitude value (must be numeric, -180 to 180).

    Returns:
        Validated float longitude.

    Raises:
        ValidationError: If value is invalid.
    """
    try:
        lng = float(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"lng must be a number. Received: {value!r}",
            param_name="lng",
        )

    if math.isnan(lng) or math.isinf(lng):
        raise ValidationError(
            f"lng must be a finite number. Received: {value!r}",
            param_name="lng",
        )

    if not (-180 <= lng <= 180):
        raise ValidationError(
            f"lng must be between -180 and 180. Received: {lng}",
            param_name="lng",
        )

    return lng


def validate_radius(value: Any, max_radius_m: int) -> int:
    """Validate and return radius value.

    Args:
        value: Radius in meters (must be numeric, 1 to max_radius_m).
        max_radius_m: Maximum allowed radius from config.

    Returns:
        Validated integer radius.

    Raises:
        ValidationError: If value is invalid.
    """
    try:
        radius = int(float(value))
    except (TypeError, ValueError):
        raise ValidationError(
            f"radius_m must be a number. Received: {value!r}",
            param_name="radius_m",
        )

    if radius < 1:
        raise ValidationError(
            f"radius_m must be between 1 and {max_radius_m}. Received: {radius}",
            param_name="radius_m",
        )

    if radius > max_radius_m:
        raise ValidationError(
            f"radius_m must be between 1 and {max_radius_m}. Received: {radius}",
            param_name="radius_m",
        )

    return radius


def validate_limit(value: Any, max_results: int = 100) -> int:
    """Validate and return limit value.

    Args:
        value: Maximum results to return (1 to max_results).
        max_results: Maximum allowed limit.

    Returns:
        Validated integer limit.

    Raises:
        ValidationError: If value is invalid.
    """
    if value is None:
        return 20  # default

    try:
        limit = int(float(value))
    except (TypeError, ValueError):
        raise ValidationError(
            f"limit must be a number. Received: {value!r}",
            param_name="limit",
        )

    if limit < 1:
        raise ValidationError(
            f"limit must be between 1 and {max_results}. Received: {limit}",
            param_name="limit",
        )

    if limit > max_results:
        raise ValidationError(
            f"limit must be between 1 and {max_results}. Received: {limit}",
            param_name="limit",
        )

    return limit


def validate_category(value: Any, valid_categories: set[str]) -> str:
    """Validate category against the cached taxonomy.

    Category is validated BEFORE reaching SQL as defense in depth against
    SQL injection. Only known-good taxonomy values pass through.

    Args:
        value: Category ID string.
        valid_categories: Set of valid category names from taxonomy.

    Returns:
        Validated category string.

    Raises:
        ValidationError: If value is not a valid category.
    """
    if not value or not isinstance(value, str):
        raise ValidationError(
            "category is required and must be a non-empty string.",
            param_name="category",
        )

    category = value.strip()
    if not category:
        raise ValidationError(
            "category must be a non-empty string.",
            param_name="category",
        )

    if category not in valid_categories:
        raise ValidationError(
            f"Unknown category: '{category}'. "
            "Use get_place_categories to find valid categories.",
            param_name="category",
        )

    return category


def validate_include_geometry(value: Any) -> bool:
    """Validate and return include_geometry boolean.

    Args:
        value: Boolean or boolean-like value.

    Returns:
        Validated boolean.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def validate_query(value: Any) -> str | None:
    """Validate the query parameter for category search.

    Args:
        value: Search string (optional).

    Returns:
        Cleaned query string or None if empty/not provided.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(
            f"query must be a string. Received: {type(value).__name__}",
            param_name="query",
        )
    query = value.strip()
    return query if query else None
