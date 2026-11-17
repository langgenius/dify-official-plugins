"""Unit tests for the stream_function_calling -> STREAM_TOOL_CALL wiring.

The credential has existed in the provider form since langgenius/dify#3467
but was never read after the plugin migration (issue #4067). It must declare
``ModelFeature.STREAM_TOOL_CALL`` only when explicitly set to ``supported``.
"""

from unittest.mock import patch

from dify_plugin.entities.model import (
    AIModelEntity,
    I18nObject,
    ModelFeature,
    ModelType,
)

from models.llm.llm import OpenAILargeLanguageModel

SUPER_SCHEMA = (
    "dify_plugin.interfaces.model.openai_compatible.llm."
    "OAICompatLargeLanguageModel.get_customizable_model_schema"
)


def _schema_features(credentials, preset_features=None):
    llm = OpenAILargeLanguageModel(model_schemas=[])

    def fake_super(self, model, creds):
        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model, zh_Hans=model),
            model_type=ModelType.LLM,
            model_properties={},
            features=list(preset_features or []),
        )

    with patch(SUPER_SCHEMA, new=fake_super):
        entity = llm.get_customizable_model_schema("my-model", credentials)

    return entity.features or []


def test_supported_declares_stream_tool_call():
    features = _schema_features({"stream_function_calling": "supported"})

    assert ModelFeature.STREAM_TOOL_CALL in features


def test_not_supported_omits_stream_tool_call():
    features = _schema_features({"stream_function_calling": "not_supported"})

    assert ModelFeature.STREAM_TOOL_CALL not in features


def test_omitted_credential_omits_stream_tool_call():
    features = _schema_features({})

    assert ModelFeature.STREAM_TOOL_CALL not in features


def test_existing_declaration_is_not_duplicated():
    features = _schema_features(
        {"stream_function_calling": "supported"},
        preset_features=[ModelFeature.STREAM_TOOL_CALL],
    )

    assert features.count(ModelFeature.STREAM_TOOL_CALL) == 1
