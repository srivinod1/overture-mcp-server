"""Unit tests for the operation registry."""

import pytest
from overture_mcp.registry import OperationDef, OperationRegistry


async def dummy_handler(**kwargs):
    return {"results": []}


def make_operation(name="test_op", theme="test", description="A test operation"):
    return OperationDef(
        name=name,
        description=description,
        theme=theme,
        parameters={
            "type": "object",
            "properties": {"lat": {"type": "number"}},
            "required": ["lat"],
        },
        handler=dummy_handler,
        example={"operation": name, "params": {"lat": 52.37}},
    )


class TestOperationRegistry:
    """Tests for OperationRegistry."""

    def test_register_and_get(self):
        registry = OperationRegistry()
        op = make_operation("places_in_radius", "places")
        registry.register(op)
        assert registry.get("places_in_radius") is op

    def test_get_unknown_returns_none(self):
        registry = OperationRegistry()
        assert registry.get("nonexistent") is None

    def test_duplicate_registration_raises(self):
        registry = OperationRegistry()
        op = make_operation("places_in_radius")
        registry.register(op)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(op)

    def test_list_operations(self):
        registry = OperationRegistry()
        registry.register(make_operation("op_a", "places", "Desc A"))
        registry.register(make_operation("op_b", "buildings", "Desc B"))

        ops = registry.list_operations()
        assert len(ops) == 2
        assert ops[0] == {"name": "op_a", "description": "Desc A", "theme": "places"}
        assert ops[1] == {"name": "op_b", "description": "Desc B", "theme": "buildings"}

    def test_list_operations_has_required_fields(self):
        registry = OperationRegistry()
        registry.register(make_operation("op_a"))
        ops = registry.list_operations()
        for op in ops:
            assert "name" in op
            assert "description" in op
            assert "theme" in op

    def test_get_schema_known(self):
        registry = OperationRegistry()
        registry.register(make_operation("places_in_radius"))
        schema = registry.get_schema("places_in_radius")
        assert schema is not None
        assert schema["name"] == "places_in_radius"
        assert "parameters" in schema
        assert "example" in schema

    def test_get_schema_unknown(self):
        registry = OperationRegistry()
        assert registry.get_schema("nonexistent") is None

    def test_get_schema_includes_example(self):
        registry = OperationRegistry()
        op = make_operation("test_op")
        registry.register(op)
        schema = registry.get_schema("test_op")
        assert "example" in schema
        assert schema["example"]["operation"] == "test_op"

    def test_operation_names(self):
        registry = OperationRegistry()
        registry.register(make_operation("op_a"))
        registry.register(make_operation("op_b"))
        assert registry.operation_names == ["op_a", "op_b"]

    def test_count(self):
        registry = OperationRegistry()
        assert registry.count == 0
        registry.register(make_operation("op_a"))
        assert registry.count == 1
        registry.register(make_operation("op_b"))
        assert registry.count == 2

    def test_contains(self):
        registry = OperationRegistry()
        registry.register(make_operation("op_a"))
        assert "op_a" in registry
        assert "op_b" not in registry

    def test_iter(self):
        registry = OperationRegistry()
        registry.register(make_operation("op_a"))
        registry.register(make_operation("op_b"))
        names = [op.name for op in registry]
        assert names == ["op_a", "op_b"]


class TestOperationDef:
    """Tests for OperationDef dataclass."""

    def test_has_required_fields(self):
        op = make_operation()
        assert hasattr(op, "name")
        assert hasattr(op, "description")
        assert hasattr(op, "theme")
        assert hasattr(op, "parameters")
        assert hasattr(op, "handler")

    def test_example_optional(self):
        op = OperationDef(
            name="test",
            description="test",
            theme="test",
            parameters={},
            handler=dummy_handler,
        )
        assert op.example is None

    def test_name_is_snake_case(self):
        """Convention: operation names should be snake_case."""
        op = make_operation("places_in_radius")
        assert op.name == op.name.lower()
        assert " " not in op.name
