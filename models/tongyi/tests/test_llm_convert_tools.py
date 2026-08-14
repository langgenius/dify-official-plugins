"""Regression tests for tool-schema handling in TongyiLargeLanguageModel._convert_tools.

`PromptMessageTool.parameters` is typed `dict` and is not validated by the SDK, so
arbitrary JSON Schema reaches `_convert_tools`. It used to index three keys without a
guard -- `parameters["properties"]`, `parameters["required"]` and, per property,
`p_val["type"]` -- so a schema omitting any of them raised a KeyError that surfaced to
the user as `InvokeError: [models] Error: '<key>'`. Because the call site is gated on
`if tools:`, Agent nodes hit this on every invocation while plain LLM nodes never did.

These tests pin the corrected behaviour:
- a property with `anyOf` and no `type` converts, and the emitted property carries no
  `type` key rather than an invented one (dify-official-plugins issue 3473),
- a tool declaring no `properties` converts,
- a tool with `properties` but no `required` converts (the line open PR 3619 also fixes),
- a well-formed tool converts to exactly the same structure as before (guard rail).

Offline by construction: `_convert_tools` is pure and runs before any network call, so
these need no credentials and perform no I/O.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dify_plugin.entities.model.message import PromptMessageTool

# Make the plugin's own modules importable when pytest is invoked from the
# plugin directory or the repo root, matching the pattern in the other
# models/tongyi/tests/ files.
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from models.llm import llm as tongyi_llm  # noqa: E402

TongyiLargeLanguageModel = tongyi_llm.TongyiLargeLanguageModel


def _model() -> "TongyiLargeLanguageModel":
    """Build the model without running ModelProvider.__init__, which would load the
    provider schema from disk. _convert_tools touches no instance state.
    """
    return TongyiLargeLanguageModel(model_schemas=MagicMock())


def _tool(parameters: dict) -> PromptMessageTool:
    return PromptMessageTool(
        name="get_weather",
        description="Look up the weather",
        parameters=parameters,
    )


def _properties_of(converted: list[dict]) -> dict:
    return converted[0]["function"]["parameters"]


def test_property_without_type_converts_and_omits_the_key() -> None:
    """The issue-3473 failure: an `anyOf` property declares no top-level `type`.

    The converted property must carry NO `type` key. Asserting the exact structure is
    the point -- what gets sent to DashScope is the load-bearing question, not merely
    that no exception escaped. Inventing `"string"` here would misdescribe a
    string-or-number parameter to the model.
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

    converted = _model()._convert_tools([tool])

    assert _properties_of(converted) == {
        "city_or_id": {"description": "City name or numeric station id"}
    }
    assert "type" not in _properties_of(converted)["city_or_id"]


def test_tool_without_properties_converts() -> None:
    """A tool taking no arguments is legal JSON Schema and used to die with
    KeyError('properties')."""
    tool = _tool({"type": "object"})

    converted = _model()._convert_tools([tool])

    assert _properties_of(converted) == {}
    assert converted[0]["function"]["required"] == []


def test_tool_without_required_converts() -> None:
    """A schema with properties but no `required` list -- the line open PR 3619 also
    guards. Our guard is byte-identical to theirs."""
    tool = _tool(
        {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
        }
    )

    converted = _model()._convert_tools([tool])

    assert converted[0]["function"]["required"] == []
    assert _properties_of(converted) == {"city": {"description": "City name", "type": "string"}}


def test_well_formed_tool_is_unchanged() -> None:
    """GUARD RAIL -- passes both before and after the fix by design.

    Proves the guards are inert on the happy path: a fully-specified schema must convert
    to exactly the structure it always did.
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

    assert converted == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Look up the weather",
                "parameters": {
                    "city": {"description": "City name", "type": "string"},
                    "unit": {
                        "description": (
                            "Temperature unit; Only accepts one of the following "
                            "predefined options: [c, f]"
                        ),
                        "type": "string",
                    },
                },
                "required": ["city"],
            },
        }
    ]


def test_enum_only_property_converts() -> None:
    """An enum-only property declares no `type`; the enum is still folded into the
    description, as it always was."""
    tool = _tool(
        {
            "type": "object",
            "properties": {"unit": {"description": "Unit", "enum": ["c", "f"]}},
            "required": [],
        }
    )

    converted = _model()._convert_tools([tool])

    assert _properties_of(converted) == {
        "unit": {
            "description": "Unit; Only accepts one of the following predefined options: [c, f]"
        }
    }


def test_empty_schema_converts() -> None:
    """The degenerate case: an entirely empty parameters dict, missing every key."""
    tool = _tool({})

    converted = _model()._convert_tools([tool])

    assert _properties_of(converted) == {}
    assert converted[0]["function"]["required"] == []


@pytest.mark.parametrize(
    "missing_key, parameters",
    [
        ("properties", {"type": "object", "required": []}),
        ("required", {"type": "object", "properties": {}}),
        ("type", {"type": "object", "properties": {"a": {"description": "d"}}}),
    ],
)
def test_no_keyerror_for_any_missing_schema_key(missing_key, parameters) -> None:
    """None of the three previously-unguarded keys may raise KeyError."""
    try:
        _model()._convert_tools([_tool(parameters)])
    except KeyError as exc:  # pragma: no cover - the assertion message is the point
        pytest.fail(f"KeyError({exc}) raised for schema missing {missing_key!r}")
