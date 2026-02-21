"""
Operation registry — central catalog of all available operations.

Both tool modes (direct and progressive) read from this registry.
Adding a new operation means:
1. Write the handler function
2. Add an entry to the registry via register_operation()

The registry stores:
- Operation name, description, and theme
- Full JSON Schema for parameters
- Handler function reference
- Example call for progressive mode's get_operation_schema
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class OperationDef:
    """Definition of a registered operation."""

    name: str
    description: str
    theme: str
    parameters: dict[str, Any]  # JSON Schema
    handler: Callable[..., Awaitable[dict[str, Any]]]
    example: dict[str, Any] | None = None


class OperationRegistry:
    """Central registry of all operations.

    Both direct and progressive tool modes read from this registry.
    Operations are registered at server startup and never change
    during the lifetime of the server.
    """

    def __init__(self):
        self._operations: dict[str, OperationDef] = {}

    def register(self, operation: OperationDef) -> None:
        """Register an operation.

        Args:
            operation: Operation definition to register.

        Raises:
            ValueError: If an operation with the same name already exists.
        """
        if operation.name in self._operations:
            raise ValueError(
                f"Operation '{operation.name}' is already registered."
            )
        self._operations[operation.name] = operation

    def get(self, name: str) -> OperationDef | None:
        """Get an operation definition by name.

        Args:
            name: Operation name.

        Returns:
            OperationDef or None if not found.
        """
        return self._operations.get(name)

    def list_operations(self) -> list[dict[str, str]]:
        """List all operations with name, description, and theme.

        Returns:
            List of dicts with name, description, and theme keys.
            Grouped by theme implicitly (registration order).
        """
        return [
            {
                "name": op.name,
                "description": op.description,
                "theme": op.theme,
            }
            for op in self._operations.values()
        ]

    def get_schema(self, name: str) -> dict[str, Any] | None:
        """Get the full schema for an operation (for progressive mode).

        Args:
            name: Operation name.

        Returns:
            Dict with name, description, parameters (JSON Schema), and example.
            None if operation not found.
        """
        op = self._operations.get(name)
        if op is None:
            return None

        result: dict[str, Any] = {
            "name": op.name,
            "description": op.description,
            "parameters": op.parameters,
        }
        if op.example is not None:
            result["example"] = op.example

        return result

    @property
    def operation_names(self) -> list[str]:
        """List of all registered operation names."""
        return list(self._operations.keys())

    @property
    def count(self) -> int:
        """Number of registered operations."""
        return len(self._operations)

    def __contains__(self, name: str) -> bool:
        """Check if an operation is registered."""
        return name in self._operations

    def __iter__(self):
        """Iterate over all operation definitions."""
        return iter(self._operations.values())
