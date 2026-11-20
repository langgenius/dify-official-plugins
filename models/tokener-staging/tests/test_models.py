from pathlib import Path
from unittest.mock import patch

import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity, I18nObject, ModelFeature, ModelType

from models._credentials import ENDPOINT_URL
from models.llm._wire import TRANSPORT_FIELDS
from models.llm.llm import TokenerLargeLanguageModel
from scripts.source_contracts import RULE_FIELDS, load_source_contracts
from scripts.sync_catalog import SOURCE_ROOT


def _schema(model: str, features: list[ModelFeature]) -> AIModelEntity:
    return AIModelEntity(
        model=model,
        label=I18nObject(en_US=model),
        model_type=ModelType.LLM,
        features=features,
        model_properties={},
    )


def test_llm_schema_only_exposes_supported_parameters() -> None:
    schemas = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in Path("models/llm").glob("*.yaml")
        if path.name != "_position.yaml"
    ]

    assert schemas
    contracts = load_source_contracts(SOURCE_ROOT)
    for schema in schemas:
        rules = {rule["name"]: rule for rule in schema["parameter_rules"]}

        source = contracts.get(schema["model"])
        if source:
            expected = {
                rule["name"]: {key: value for key, value in rule.items() if key in RULE_FIELDS}
                for rule in source["model"].get("parameter_rules", [])
                if rule["name"] not in TRANSPORT_FIELDS
            }
            assert {name: rules[name] for name in expected} == expected
        else:
            assert rules["max_tokens"]["min"] == 1
            assert rules["max_tokens"]["max"] >= rules["max_tokens"]["default"] >= 1


@patch.object(OAICompatLargeLanguageModel, "_invoke", return_value="llm-result")
def test_llm_enables_tool_calls_for_tool_models(invoke) -> None:
    model = TokenerLargeLanguageModel(
        model_schemas=[_schema("tool-model", [ModelFeature.TOOL_CALL])]
    )
    credentials = {"api_key": "test-key"}

    result = model._invoke(
        model="tool-model",
        credentials=credentials,
        prompt_messages=[],
        model_parameters={"temperature": 0.2},
        stream=False,
        user="user-1",
    )

    assert result == "llm-result"
    assert credentials == {"api_key": "test-key"}
    invoke.assert_called_once_with(
        model="tool-model",
        credentials={
            "api_key": "test-key",
            "endpoint_url": ENDPOINT_URL,
            "mode": "chat",
            "function_calling_type": "tool_call",
        },
        prompt_messages=[],
        model_parameters={"temperature": 0.2},
        tools=None,
        stop=None,
        stream=False,
        user="user-1",
    )


@patch.object(OAICompatLargeLanguageModel, "_invoke", return_value="llm-result")
def test_llm_omits_tool_calls_for_plain_models(invoke) -> None:
    model = TokenerLargeLanguageModel(model_schemas=[_schema("plain-model", [])])

    model._invoke(
        model="plain-model",
        credentials={"api_key": "test-key"},
        prompt_messages=[],
        model_parameters={},
        stream=False,
    )

    assert invoke.call_args.kwargs["credentials"] == {
        "api_key": "test-key",
        "endpoint_url": ENDPOINT_URL,
        "mode": "chat",
    }
