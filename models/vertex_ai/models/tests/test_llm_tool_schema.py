import os
import sys

from dify_plugin.entities.model.message import PromptMessageTool
from google.genai import types

try:
    from models.llm.llm import VertexAiLargeLanguageModel
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from models.llm.llm import VertexAiLargeLanguageModel


def test_empty_tool_parameters_are_omitted():
    llm = VertexAiLargeLanguageModel([])
    tool = PromptMessageTool(
        name="ping",
        description="Ping an external service",
        parameters={"type": "object", "properties": {}},
    )

    genai_tool = llm._convert_tools_to_genai_tool([tool])

    declaration = genai_tool.function_declarations[0]
    assert isinstance(declaration, types.FunctionDeclaration)
    assert declaration.parameters is None


def test_tool_parameters_are_typed_genai_schema_objects():
    llm = VertexAiLargeLanguageModel([])
    tool = PromptMessageTool(
        name="search",
        description="Search documents",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Maximum results"},
                "mode": {"type": "select", "enum": ["fast", "full"]},
                "filters": {
                    "type": "object",
                    "properties": {
                        "archived": {"type": "boolean"},
                    },
                    "required": ["archived"],
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "note": {"type": "string", "nullable": True},
                "optional_count": {"type": ["integer", "null"]},
            },
            "required": ["query"],
        },
    )

    genai_tool = llm._convert_tools_to_genai_tool([tool])

    parameters = genai_tool.function_declarations[0].parameters
    assert isinstance(parameters, types.Schema)
    assert parameters.type == types.Type.OBJECT
    assert parameters.required == ["query"]
    assert parameters.properties["query"].type == types.Type.STRING
    assert parameters.properties["limit"].type == types.Type.INTEGER
    assert parameters.properties["mode"].type == types.Type.STRING
    assert parameters.properties["mode"].enum == ["fast", "full"]
    assert parameters.properties["filters"].type == types.Type.OBJECT
    assert parameters.properties["filters"].required == ["archived"]
    assert (
        parameters.properties["filters"].properties["archived"].type
        == types.Type.BOOLEAN
    )
    assert parameters.properties["tags"].type == types.Type.ARRAY
    assert parameters.properties["tags"].items.type == types.Type.STRING
    assert parameters.properties["note"].nullable is True
    assert parameters.properties["optional_count"].type == types.Type.INTEGER
    assert parameters.properties["optional_count"].nullable is True


def test_tool_parameters_infer_missing_schema_types():
    llm = VertexAiLargeLanguageModel([])
    tool = PromptMessageTool(
        name="search",
        description="Search documents",
        parameters={
            "properties": {
                "filters": {
                    "properties": {
                        "labels": {
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    )

    genai_tool = llm._convert_tools_to_genai_tool([tool])

    parameters = genai_tool.function_declarations[0].parameters
    assert parameters.type == types.Type.OBJECT
    assert parameters.properties["filters"].type == types.Type.OBJECT
    assert parameters.properties["filters"].properties["labels"].type == types.Type.ARRAY
    assert (
        parameters.properties["filters"].properties["labels"].items.type
        == types.Type.STRING
    )
