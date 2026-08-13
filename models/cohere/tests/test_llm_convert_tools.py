"""Regression tests for tool-schema handling in CohereLargeLanguageModel._convert_tools.

`PromptMessageTool.parameters` is typed `dict` and is not validated by the SDK, so
arbitrary JSON Schema reaches `_convert_tools`. It used to index four keys without a
guard -- `parameters["properties"]`, `parameters["required"]`, and per property
`p_val["description"]` and `p_val["type"]` -- so a schema omitting any of them raised a
KeyError on the invocation path.

Unlike the equivalent fix in the tongyi plugin, a missing `type` cannot simply be omitted
here: `cohere.ToolParameterDefinitionsValue.type` is a required, non-Optional `str`, and
the SDK validates client-side (omitting it raises "field required"; passing None raises
"none is not an allowed value"). The guard therefore falls back to the most permissive
type rather than dropping the key.

This defect is LATENT -- found by audit, with no user report and no field reproduction.

Offline by construction: `_convert_tools` is pure and runs before any network call, so
these need no credentials and perform no I/O.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dify_plugin.entities.model.message import PromptMessageTool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm.llm import CohereLargeLanguageModel  # noqa: E402


def _model() -> CohereLargeLanguageModel:
    return CohereLargeLanguageModel(model_schemas=MagicMock())


def _tool(parameters: dict) -> PromptMessageTool:
    return PromptMessageTool(
        name="get_weather",
        description="Look up the weather",
        parameters=parameters,
    )


def _definitions(converted: list):
    return converted[0].parameter_definitions


def test_property_without_type_converts_with_permissive_fallback() -> None:
    """A property declaring no top-level `type` (here via `anyOf`).

    The Cohere SDK requires `type` to be a non-empty string, so unlike the tongyi fix this
    one supplies a fallback rather than omitting the key. The exact emitted value is
    asserted because it is what reaches the Cohere API.
    """
    tool = _tool(
        {
            "type": "object",
            "properties": {
                "city_or_id": {
                    "description": "City name or numeric station id",
                    "anyOf": [{"type": "string"}, {"type": "integer"}],
                }
            },
            "required": ["city_or_id"],
        }
    )

    definitions = _definitions(_model()._convert_tools([tool]))

    assert definitions["city_or_id"].type == "string"
    assert definitions["city_or_id"].description == "City name or numeric station id"
    assert definitions["city_or_id"].required is True


def test_property_without_description_converts() -> None:
    """Cohere subscripted `description` where tongyi already used `.get()`; a property
    with no description used to raise KeyError('description')."""
    tool = _tool(
        {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": [],
        }
    )

    definitions = _definitions(_model()._convert_tools([tool]))

    assert definitions["city"].description == ""
    assert definitions["city"].type == "string"


def test_tool_without_properties_converts() -> None:
    """A tool taking no arguments is legal JSON Schema."""
    tool = _tool({"type": "object"})

    assert _definitions(_model()._convert_tools([tool])) == {}


def test_tool_without_required_converts() -> None:
    """A schema with properties but no `required` list."""
    tool = _tool(
        {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
        }
    )

    definitions = _definitions(_model()._convert_tools([tool]))

    assert definitions["city"].required is False


def test_empty_schema_converts() -> None:
    """The degenerate case: every key missing at once."""
    tool = _tool({})

    assert _definitions(_model()._convert_tools([tool])) == {}


def test_enum_only_property_converts() -> None:
    """An enum-only property declares no `type`; the enum still folds into the
    description, and the fallback type applies."""
    tool = _tool(
        {
            "type": "object",
            "properties": {"unit": {"description": "Unit", "enum": ["c", "f"]}},
            "required": [],
        }
    )

    definitions = _definitions(_model()._convert_tools([tool]))

    assert definitions["unit"].description == (
        "Unit; Only accepts one of the following predefined options: [c, f]"
    )
    assert definitions["unit"].type == "string"


def test_well_formed_tool_is_unchanged() -> None:
    """GUARD RAIL -- passes both before and after the fix by design.

    Proves the guards are inert on the happy path.
    """
    tool = _tool(
        {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
                "unit": {
                    "type": "string",
                    "description": "Temperature unit",
                    "enum": ["c", "f"],
                },
            },
            "required": ["city"],
        }
    )

    converted = _model()._convert_tools([tool])

    assert converted[0].name == "get_weather"
    assert converted[0].description == "Look up the weather"
    definitions = converted[0].parameter_definitions
    assert definitions["city"].description == "City name"
    assert definitions["city"].type == "string"
    assert definitions["city"].required is True
    assert definitions["unit"].description == (
        "Temperature unit; Only accepts one of the following predefined options: [c, f]"
    )
    assert definitions["unit"].type == "string"
    assert definitions["unit"].required is False


@pytest.mark.parametrize(
    "missing_key, parameters",
    [
        ("properties", {"type": "object", "required": []}),
        ("required", {"type": "object", "properties": {}}),
        ("description", {"type": "object", "properties": {"a": {"type": "string"}}}),
        ("type", {"type": "object", "properties": {"a": {"description": "d"}}}),
    ],
)
def test_no_keyerror_for_any_missing_schema_key(missing_key, parameters) -> None:
    """None of the four previously-unguarded keys may raise KeyError."""
    try:
        _model()._convert_tools([_tool(parameters)])
    except KeyError as exc:  # pragma: no cover - the assertion message is the point
        pytest.fail(f"KeyError({exc}) raised for schema missing {missing_key!r}")
