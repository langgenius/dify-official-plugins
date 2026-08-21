from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    UserPromptMessage,
)
from models.llm.llm import OpenAILargeLanguageModel


def test_normalize_domains():
    raw = "https://openai.com, github.com/test, https://docs.dify.ai:443, openai.com"
    normalized = OpenAILargeLanguageModel._normalize_domains(raw)
    assert normalized == ["openai.com", "github.com", "docs.dify.ai"]


def test_extract_responses_web_search_config():
    model = OpenAILargeLanguageModel(model_schemas=[])
    params = {
        "web_search": True,
        "web_search_allowed_domains": "openai.com, github.com",
        "web_search_blocked_domains": "reddit.com",
        "web_search_context_size": "high",
        "web_search_user_country": "US",
    }
    creds = {"api_type": "responses"}
    config = model._extract_responses_web_search_config(params, creds)
    assert config is not None
    assert config["type"] == "web_search"
    assert config["filters"]["allowed_domains"] == ["openai.com", "github.com"]
    assert config["filters"]["blocked_domains"] == ["reddit.com"]
    assert config["search_context_size"] == "high"
    assert config["user_location"] == {"type": "approximate", "country": "US"}


def test_responses_api_schema_rules():
    model = OpenAILargeLanguageModel(model_schemas=[])
    creds = {
        "api_type": "responses",
        "mode": "chat",
        "context_size": "4096",
    }
    schema = model.get_customizable_model_schema("gpt-5", creds)
    param_names = [rule.name for rule in schema.parameter_rules]
    assert "web_search" in param_names
    assert "web_search_allowed_domains" in param_names
    assert "web_search_blocked_domains" in param_names
    assert "web_search_context_size" in param_names
    assert "web_search_user_country" in param_names


def test_chat_completions_schema_rules_without_responses():
    model = OpenAILargeLanguageModel(model_schemas=[])
    # When api_type is chat_completions and web_search_support is not_supported
    creds = {
        "api_type": "chat_completions",
        "web_search_support": "not_supported",
        "mode": "chat",
        "context_size": "4096",
    }
    schema = model.get_customizable_model_schema("gpt-5", creds)
    param_names = [rule.name for rule in schema.parameter_rules]
    assert "web_search" not in param_names
    assert "web_search_allowed_domains" not in param_names
    assert "web_search_blocked_domains" not in param_names
    assert "web_search_context_size" not in param_names
    assert "web_search_user_country" not in param_names

    # When web_search_support is tool_standard but api_type is chat_completions
    creds["web_search_support"] = "tool_standard"
    schema2 = model.get_customizable_model_schema("gpt-5", creds)
    param_names2 = [rule.name for rule in schema2.parameter_rules]
    assert "web_search" in param_names2
    # Domain filtering should NOT appear because api_type is NOT responses
    assert "web_search_allowed_domains" not in param_names2
    assert "web_search_blocked_domains" not in param_names2
    assert "web_search_context_size" not in param_names2
    assert "web_search_user_country" not in param_names2


def test_invoke_routes_to_responses_api():
    model = OpenAILargeLanguageModel(model_schemas=[])
    prompt_messages = [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(content="Hello"),
    ]
    creds = {
        "api_type": "responses",
        "endpoint_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
        "mode": "chat",
    }
    params = {
        "web_search": True,
        "web_search_allowed_domains": "openai.com",
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output = [MagicMock(type="message", content="Hello! How can I help you today?")]
    mock_response.usage = MagicMock(input_tokens=10, output_tokens=12)
    mock_client.responses.create.return_value = mock_response

    with patch.object(model, "_create_openai_client", return_value=mock_client):
        result = model._invoke(
            model="gpt-5",
            credentials=creds,
            prompt_messages=prompt_messages,
            model_parameters=params,
            stream=False,
        )

    assert mock_client.responses.create.called
    call_kwargs = mock_client.responses.create.call_args[1]
    assert call_kwargs["model"] == "gpt-5"
    assert any(t.get("type") == "web_search" for t in call_kwargs["tools"])
    assert result.message.content == "Hello! How can I help you today?"
