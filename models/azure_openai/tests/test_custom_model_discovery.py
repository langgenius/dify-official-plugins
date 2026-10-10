"""Offline unit tests for the azure_openai custom-model discovery feature.

Covers, without any network access or API key:

- ``uses_responses_api`` version-agnostic routing (gpt-6+)
- Custom base-model resolution and the synthetic entity schema
- validation ping matrix (reasoning models omit temperature; responses uses
  max_output_tokens; chat uses max_tokens)
- token counting fallbacks for unknown/custom families (no NotImplementedError)
- advisory model-catalogue cache (fail-soft, TTL, bounded)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

import models.llm.llm as llm_module
from models.llm import llm as azure_llm
from models.llm.llm import (
    _list_available_models,
    _available_models_cache,
)
from models.constants import uses_responses_api


def _creds(**overrides) -> dict:
    base = {
        "openai_api_base": "https://example.openai.azure.com/",
        "auth_method": "api_key",
        "openai_api_key": "key",
        "openai_api_version": "2025-04-01-preview",
        "base_model_name": "gpt-5",
    }
    base.update(overrides)
    return base


def _model() -> azure_llm.AzureOpenAILargeLanguageModel:
    return azure_llm.AzureOpenAILargeLanguageModel(model_schemas=[])


# ---------------------------------------------------------------------------
# Routing: version-agnostic Responses detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("gpt-5", True),
        ("gpt-5.5", True),
        ("gpt-5.6-sol", True),
        ("gpt-6", True),
        ("gpt-6-luna", True),
        ("gpt-6-chat", False),
        ("gpt-6-codex", True),
        ("gpt-10", True),
        ("gpt-4o", False),
        ("gpt-35-turbo", False),
        ("gpt-35-turbo-16k", False),
        ("gpt-35-turbo-instruct", False),
        ("o4-mini", False),
    ],
)
def test_uses_responses_api_gpt_families(name, expected):
    assert uses_responses_api(name) is expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("o1", True),
        ("o1-preview", True),
        ("o3-mini", True),
        ("o4-mini", True),
        ("O1", True),
        ("gpt-5", True),
        ("gpt-6", True),
        ("gpt-6-chat", False),
        ("gpt-6-codex", False),
        ("gpt-4o", False),
        ("gpt-35-turbo", False),
        ("gpt-35-turbo-16k", False),
        ("gpt-35-turbo-instruct", False),
        ("custom-chat", False),
        ("", False),
        (None, False),
    ],
)
def test_is_reasoning_family(name, expected):
    from models.llm.llm import _is_reasoning_family

    assert _is_reasoning_family(name) is expected


def test_custom_base_model_resolution():
    model = _model()
    assert (
        model._effective_base_model_name(_creds()) == "gpt-5"
    )
    custom = _creds(base_model_name="Custom", custom_base_model_name="gpt-6")
    assert model._effective_base_model_name(custom) == "gpt-6"
    # deployment name is never used for routing; names are lowercased
    assert model._effective_base_model_name(
        _creds(base_model_name="Custom", custom_base_model_name="")
    ) == "custom"


def test_effective_base_model_name_lowercases():
    model = _model()
    assert (
        model._effective_base_model_name(
            _creds(base_model_name="Custom", custom_base_model_name="O1")
        )
        == "o1"
    )
    assert (
        model._effective_base_model_name(
            _creds(base_model_name="Custom", custom_base_model_name="GPT-6")
        )
        == "gpt-6"
    )


def test_clear_illegal_prompt_messages_uppercase_reasoning():
    from dify_plugin.entities.model.message import (
        SystemPromptMessage,
        UserPromptMessage,
    )

    model = _model()
    messages = model._clear_illegal_prompt_messages(
        "O1", [SystemPromptMessage(content="sys")]
    )
    assert all(isinstance(m, UserPromptMessage) for m in messages)


def test_clear_illegal_prompt_messages_mixed_case_checklist():
    from dify_plugin.entities.model.message import (
        TextPromptMessageContent,
        UserPromptMessage,
    )

    model = _model()
    messages = model._clear_illegal_prompt_messages(
        "GPT-4-TURBO",
        [
            UserPromptMessage(content=[TextPromptMessageContent(data="a")]),
            UserPromptMessage(content=[TextPromptMessageContent(data="b")]),
        ],
    )
    user = [m for m in messages if isinstance(m, UserPromptMessage)]
    # checklist applies: list content is collapsed into plain strings
    assert all(isinstance(m.content, str) for m in user)
    assert user[0].content == "a"
    assert user[1].content == "b"


def test_custom_selection_case_insensitive():
    from dify_plugin.errors.model import CredentialsValidateFailedError

    model = _model()
    # lowercase "custom" still routes via custom_base_model_name
    assert (
        model._effective_base_model_name(
            _creds(base_model_name="custom", custom_base_model_name="gpt-6")
        )
        == "gpt-6"
    )
    # and validation still rejects a blank custom base
    with patch.object(model, "_create_client") as client_mock:
        with pytest.raises(CredentialsValidateFailedError):
            model.validate_credentials(
                "d", _creds(base_model_name="custom", custom_base_model_name="")
            )
    client_mock.assert_not_called()


def test_validate_credentials_rejects_blank_base_model_name():
    from dify_plugin.errors.model import CredentialsValidateFailedError

    model = _model()
    with patch.object(model, "_create_client") as client_mock:
        with pytest.raises(
            CredentialsValidateFailedError, match="Base Model Name is required"
        ):
            model.validate_credentials("d", _creds(base_model_name=""))
    client_mock.assert_not_called()


def test_validate_credentials_rejects_blank_custom_base():
    from dify_plugin.errors.model import CredentialsValidateFailedError

    model = _model()
    with patch.object(model, "_create_client") as client_mock:
        with pytest.raises(CredentialsValidateFailedError, match="Custom Base Model is required"):
            model.validate_credentials(
                "d", _creds(base_model_name="Custom", custom_base_model_name="")
            )
    client_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Synthetic entity for Custom / unknown base models
# ---------------------------------------------------------------------------


def test_customizable_model_schema_custom():
    from dify_plugin.entities.model import ModelPropertyKey

    model = _model()
    entity = model.get_customizable_model_schema(
        "my-deployment",
        _creds(base_model_name="Custom", custom_base_model_name="gpt-6"),
    )
    assert entity is not None
    assert entity.model == "my-deployment"
    assert entity.model_properties[ModelPropertyKey.MODE] == "chat"
    assert entity.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 128000
    rule_names = [r.name for r in entity.parameter_rules]
    # generic parameter set mirrors the curated frontier models
    for name in (
        "response_format",
        "json_schema",
        "reasoning_effort",
        "reasoning_summary",
        "verbosity",
        "max_tokens",
    ):
        assert name in rule_names
    max_tokens = next(r for r in entity.parameter_rules if r.name == "max_tokens")
    assert max_tokens.name == "max_tokens"
    # reasoning_effort must have no default: Dify injects defaults, and
    # pre-gpt-5.1 reasoning models reject effort="none"
    reasoning_effort = next(
        r for r in entity.parameter_rules if r.name == "reasoning_effort"
    )
    assert reasoning_effort.default is None
    # verbosity/reasoning_summary also must not default: Dify would inject
    # them on every call, breaking models that don't support them
    verbosity = next(r for r in entity.parameter_rules if r.name == "verbosity")
    assert verbosity.default is None
    reasoning_summary = next(
        r for r in entity.parameter_rules if r.name == "reasoning_summary"
    )
    assert reasoning_summary.default is None


def test_customizable_model_schema_context_override():
    from dify_plugin.entities.model import ModelPropertyKey

    model = _model()
    entity = model.get_customizable_model_schema(
        "d",
        _creds(
            base_model_name="Custom",
            custom_base_model_name="gpt-6",
            context_size="128000",
            max_tokens="8192",
        ),
    )
    assert entity.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 128000
    max_tokens = next(r for r in entity.parameter_rules if r.name == "max_tokens")
    assert max_tokens.max == 8192


def test_customizable_model_schema_bad_numbers_fall_back():
    from dify_plugin.entities.model import ModelPropertyKey

    model = _model()
    entity = model.get_customizable_model_schema(
        "d",
        _creds(
            base_model_name="Custom",
            custom_base_model_name="gpt-6",
            context_size="128k",
            max_tokens="-5",
        ),
    )
    assert entity.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 128000
    max_tokens = next(r for r in entity.parameter_rules if r.name == "max_tokens")
    assert max_tokens.max == 16384


# ---------------------------------------------------------------------------
# Validation ping matrix (no network: mocked client)
# ---------------------------------------------------------------------------


def test_validate_credentials_responses_ping():
    model = _model()
    client = Mock()
    client.models.list.side_effect = Exception("no catalog")  # advisory fails
    with patch.object(model, "_create_client", return_value=client):
        with patch.object(model, "_ensure_responses_api_supported") as ensure:
            model.validate_credentials(
                "my-deployment", _creds(base_model_name="gpt-6", custom_base_model_name="gpt-6")
            )
    ensure.assert_called_once()
    client.responses.create.assert_called_once()
    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["model"] == "my-deployment"
    assert kwargs["max_output_tokens"] == 16
    assert "temperature" not in kwargs


def test_validate_credentials_reasoning_chat_omits_temperature():
    model = _model()
    client = Mock()
    client.models.list.side_effect = Exception("no catalog")
    with patch.object(model, "_create_client", return_value=client):
        model.validate_credentials("d", _creds(base_model_name="o1"))
    client.chat.completions.create.assert_called_once()
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["max_completion_tokens"] == 16
    assert "temperature" not in kwargs


def test_validate_credentials_gpt6_chat_standard_ping():
    model = _model()
    client = Mock()
    client.models.list.side_effect = Exception("no catalog")
    with patch.object(model, "_create_client", return_value=client):
        model.validate_credentials(
            "d", _creds(base_model_name="gpt-6-chat")
        )
    client.chat.completions.create.assert_called_once()
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 16
    assert kwargs["temperature"] == 0


def test_validate_credentials_custom_chat_ping():
    model = _model()
    client = Mock()
    client.models.list.side_effect = Exception("no catalog")
    with patch.object(model, "_create_client", return_value=client):
        model.validate_credentials(
            "d", _creds(base_model_name="Custom", custom_base_model_name="custom-chat")
        )
    client.chat.completions.create.assert_called_once()
    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == 16


def test_chat_generate_reasoning_maps_max_tokens():
    from dify_plugin.entities.model.message import UserPromptMessage

    model = _model()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()
    model._create_client = Mock(return_value=mock_client)
    model._handle_chat_generate_response = Mock(return_value="ok")
    model._clear_illegal_prompt_messages = Mock(side_effect=lambda _, msgs: msgs)
    with patch.object(
        llm_module, "apply_dify_metadata_if_enabled", lambda *a, **k: None
    ):
        model._chat_generate(
            model="deploy",
            credentials=_creds(
                base_model_name="Custom", custom_base_model_name="o1"
            ),
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={
                "max_tokens": 4096,
                "temperature": 0.7,
                "top_p": 0.9,
                "verbosity": "medium",
                "reasoning_summary": "auto",
            },
            stop=["STOP"],
            stream=False,
        )
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["max_completion_tokens"] == 4096
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "stop" not in kwargs
    # verbosity is accepted on the versionless chat route (verified live);
    # reasoning_summary is Responses-API-only and must be dropped
    assert kwargs["verbosity"] == "medium"
    assert "reasoning_summary" not in kwargs


def test_chat_generate_standard_forwards_effort_drops_summary():
    from dify_plugin.entities.model.message import UserPromptMessage

    model = _model()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()
    model._create_client = Mock(return_value=mock_client)
    model._handle_chat_generate_response = Mock(return_value="ok")
    model._clear_illegal_prompt_messages = Mock(side_effect=lambda _, msgs: msgs)
    with patch.object(
        llm_module, "apply_dify_metadata_if_enabled", lambda *a, **k: None
    ):
        model._chat_generate(
            model="deploy",
            credentials=_creds(
                base_model_name="Custom", custom_base_model_name="custom-chat"
            ),
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={
                "max_tokens": 512,
                "reasoning_effort": "high",
                "verbosity": "high",
                "reasoning_summary": "concise",
            },
            stream=False,
        )
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 512
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["verbosity"] == "high"
    assert "reasoning_summary" not in kwargs


def test_chat_generate_o1_mini_drops_reasoning_effort():
    from dify_plugin.entities.model.message import UserPromptMessage

    model = _model()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()
    model._create_client = Mock(return_value=mock_client)
    model._handle_chat_generate_response = Mock(return_value="ok")
    model._clear_illegal_prompt_messages = Mock(side_effect=lambda _, msgs: msgs)
    with patch.object(
        llm_module, "apply_dify_metadata_if_enabled", lambda *a, **k: None
    ):
        model._chat_generate(
            model="deploy",
            credentials=_creds(
                base_model_name="Custom", custom_base_model_name="o1-mini"
            ),
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={"reasoning_effort": "low"},
            stream=False,
        )
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "reasoning_effort" not in kwargs


def test_chat_generate_json_schema_never_leaks():
    from dify_plugin.entities.model.message import UserPromptMessage

    model = _model()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()
    model._create_client = Mock(return_value=mock_client)
    model._handle_chat_generate_response = Mock(return_value="ok")
    model._clear_illegal_prompt_messages = Mock(side_effect=lambda _, msgs: msgs)
    with patch.object(
        llm_module, "apply_dify_metadata_if_enabled", lambda *a, **k: None
    ):
        # response_format=text with json_schema still in params: must not leak
        model._chat_generate(
            model="deploy",
            credentials=_creds(base_model_name="gpt-4o"),
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={
                "response_format": "text",
                "json_schema": '{"type":"object"}',
            },
            stream=False,
        )
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "json_schema" not in kwargs
    assert kwargs["response_format"] == {"type": "text"}
    # positive case: json_schema mode builds the schema into response_format
    mock_client.chat.completions.create.reset_mock()
    with patch.object(
        llm_module, "apply_dify_metadata_if_enabled", lambda *a, **k: None
    ):
        model._chat_generate(
            model="deploy",
            credentials=_creds(base_model_name="gpt-4o"),
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={
                "response_format": "json_schema",
                "json_schema": '{"type":"object","properties":{"a":{"type":"string"}}}',
            },
            stream=False,
        )
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "json_schema" not in kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["type"] == "object"


def test_validate_credentials_error_suggests_available_models():
    model = _model()
    client = Mock()
    client.responses.create.side_effect = Exception("Deployment not found")
    client.models.list.return_value = SimpleNamespace(
        data=[SimpleNamespace(id="gpt-6-luna"), SimpleNamespace(id="gpt-4o")]
    )
    with patch.object(model, "_create_client", return_value=client):
        with pytest.raises(Exception) as exc_info:
            model.validate_credentials("d", _creds(base_model_name="gpt-6"))
    assert "Available models in this resource" in str(exc_info.value)
    assert "gpt-6-luna" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Token counting fallbacks
# ---------------------------------------------------------------------------


def test_num_tokens_custom_model_no_crash():
    model = _model()
    from dify_plugin.entities.model.message import UserPromptMessage

    n = model.get_num_tokens(
        "my-deployment",
        _creds(base_model_name="Custom", custom_base_model_name="gpt-6"),
        [UserPromptMessage(content="hello world")],
    )
    assert n > 0


def test_num_tokens_from_string_fallback_o200k():
    model = _model()
    assert (
        model._num_tokens_from_string(
            _creds(base_model_name="Custom", custom_base_model_name="gpt-6"),
            "hello world",
        )
        > 0
    )


# ---------------------------------------------------------------------------
# Advisory catalogue cache
# ---------------------------------------------------------------------------


def test_list_available_models_ok_and_cached():
    client = Mock()
    client.models.list.return_value = SimpleNamespace(
        data=[SimpleNamespace(id="gpt-6"), SimpleNamespace(id="gpt-4o")]
    )
    creds = _creds()
    _available_models_cache.clear()
    assert _list_available_models(creds, client) == ["gpt-6", "gpt-4o"]
    # second call served from cache (client not called again)
    client.models.list.reset_mock()
    assert _list_available_models(creds, client) == ["gpt-6", "gpt-4o"]
    client.models.list.assert_not_called()


def test_list_available_models_fail_soft():
    client = Mock()
    client.models.list.side_effect = Exception("blocked by gateway")
    _available_models_cache.clear()
    assert _list_available_models(_creds(), client) == []


def test_list_available_models_failure_not_cached():
    client = Mock()
    client.models.list.side_effect = Exception("blocked by gateway")
    _available_models_cache.clear()
    assert _list_available_models(_creds(), client) == []
    # transient failure must be retried on next call (not cached as absence)
    client.models.list.side_effect = None
    client.models.list.return_value = SimpleNamespace(
        data=[SimpleNamespace(id="gpt-6")]
    )
    assert _list_available_models(_creds(), client) == ["gpt-6"]


def test_list_available_models_none_credentials():
    client = Mock()
    client.models.list.return_value = SimpleNamespace(data=[])
    _available_models_cache.clear()
    creds = _creds(openai_api_key=None, openai_api_version=None)
    # must not raise TypeError when credential values are None
    assert _list_available_models(creds, client) == []
