"""
Standard response envelope builder.

All operations return the same envelope structure regardless of tool mode.
This module is the single place that defines and constructs response objects.
"""

from __future__ import annotations

from typing import Any


def success_response(
    results: list[dict[str, Any]],
    query_params: dict[str, Any],
    data_version: str,
    suggestion: str | None = None,
) -> dict[str, Any]:
    """Build a standard success response envelope.

    Args:
        results: List of result objects (operation-specific).
        query_params: Echo of the input parameters.
        data_version: Overture release version used.
        suggestion: Hint when results are empty. None when results exist.

    Returns:
        Standard response envelope dict.
    """
    # Suggestion is only set when results are empty
    if results and suggestion is not None:
        suggestion = None

    return {
        "results": results,
        "count": len(results),
        "query_params": query_params,
        "data_version": data_version,
        "suggestion": suggestion,
    }


def empty_response(
    query_params: dict[str, Any],
    data_version: str,
    suggestion: str,
) -> dict[str, Any]:
    """Build a response for zero results.

    Convenience wrapper around success_response for empty results.
    Zero results is valid data, not an error.

    Args:
        query_params: Echo of the input parameters.
        data_version: Overture release version used.
        suggestion: Helpful hint for the agent (e.g., "Try increasing radius").

    Returns:
        Standard response envelope with empty results array.
    """
    return success_response(
        results=[],
        query_params=query_params,
        data_version=data_version,
        suggestion=suggestion,
    )


def error_response(
    error: str,
    error_type: str,
    query_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard error response.

    Args:
        error: Human-readable description of the error.
        error_type: One of: validation_error, query_timeout, internal_error, auth_error.
        query_params: Echo of input parameters (when available).

    Returns:
        Error response dict.
    """
    valid_error_types = {"validation_error", "query_timeout", "internal_error", "auth_error"}
    if error_type not in valid_error_types:
        raise ValueError(
            f"Invalid error_type: '{error_type}'. "
            f"Must be one of: {', '.join(sorted(valid_error_types))}"
        )

    response: dict[str, Any] = {
        "error": error,
        "error_type": error_type,
    }
    if query_params is not None:
        response["query_params"] = query_params

    return response
