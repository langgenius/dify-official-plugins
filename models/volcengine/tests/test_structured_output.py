import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import InvokeError

from models.llm.llm import (
    build_chat_completion_request,
    build_response_format,
)


GA_MODEL = "deepseek-v4-flash-ga-260731"
SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
    },
    "required": ["answer"],
    "additionalProperties": False,
}


def test_response_format_defaults_to_none() -> None:
    assert build_response_format({}) is None
    assert build_response_format({"response_format": "text"}) is None
    assert build_response_format({"response_format": ""}) is None


def test_response_format_json_object_payload() -> None:
    response_format = build_response_format({"response_format": "json_object"})
    assert response_format is not None
    assert response_format.to_payload() == {"type": "json_object"}


def test_response_format_json_schema_from_string() -> None:
    response_format = build_response_format(
        {"response_format": "json_schema", "json_schema": json.dumps(SCHEMA)}
    )
    assert response_format is not None
    assert response_format.to_payload() == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": SCHEMA},
    }


def test_response_format_json_schema_from_dict() -> None:
    response_format = build_response_format(
        {"response_format": "json_schema", "json_schema": SCHEMA}
    )
    assert response_format is not None
    payload = response_format.to_payload()
    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["schema"] == SCHEMA


def test_response_format_rejects_unknown_type() -> None:
    with pytest.raises(InvokeError, match="Invalid response_format"):
        build_response_format({"response_format": "xml"})


def test_response_format_json_schema_requires_schema() -> None:
    with pytest.raises(InvokeError, match="json_schema"):
        build_response_format({"response_format": "json_schema"})
    with pytest.raises(InvokeError, match="json_schema"):
        build_response_format({"response_format": "json_schema", "json_schema": "{}"})


def test_response_format_json_schema_rejects_invalid_json() -> None:
    with pytest.raises(InvokeError, match="not valid JSON"):
        build_response_format(
            {"response_format": "json_schema", "json_schema": "{invalid"}
        )


def test_chat_request_includes_response_format() -> None:
    request = build_chat_completion_request(
        model=GA_MODEL,
        prompt_messages=[UserPromptMessage(content="hi")],
        model_parameters={
            "response_format": "json_schema",
            "json_schema": SCHEMA,
        },
        tools=None,
        stop=None,
        user=None,
    )
    payload = request.to_payload()
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": SCHEMA},
    }


def test_chat_request_omits_response_format_by_default() -> None:
    request = build_chat_completion_request(
        model=GA_MODEL,
        prompt_messages=[UserPromptMessage(content="hi")],
        model_parameters={},
        tools=None,
        stop=None,
        user=None,
    )
    assert "response_format" not in request.to_payload()


def test_ga_model_yaml_declares_structured_output() -> None:
    models_dir = Path(__file__).resolve().parents[1] / "models" / "llm"
    schema = yaml.safe_load(
        (models_dir / f"{GA_MODEL}.yaml").read_text(encoding="utf-8")
    )
    assert "structured-output" in schema["features"]

    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
    response_format = rules["response_format"]
    assert response_format["options"] == ["text", "json_object", "json_schema"]
    json_schema = rules["json_schema"]
    assert json_schema["use_template"] == "json_schema"
