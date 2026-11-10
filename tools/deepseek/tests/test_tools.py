import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
from dify_plugin import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from provider.deepseek import DeepSeekProvider
from tools.fetch import DeepSeekFetchTool
from tools.search import DeepSeekSearchTool


def _response(data, status=200):
    return Mock(ok=status < 400, status_code=status, json=Mock(return_value=data))


def _invoke(tool, parameters):
    return list(tool.from_credentials({"api_key": "test-secret"}).invoke(parameters))


def test_search_request_and_full_results_are_preserved():
    data = {
        "results": [
            {
                "title": "文档",
                "url": "https://example.com",
                "summary": "摘要",
                "content": "# 正文",
                "authority": 3,
                "rerank_score": 2.4,
            }
        ]
    }
    parameters = {
        "query": "DeepSeek site:github.com",
        "count": 5.0,
        "need_content": True,
        "ori_question": "最新消息是什么？",
        "localization": "1.1.1.1",
    }
    with patch("requests.request", return_value=_response(data)) as request:
        messages = _invoke(DeepSeekSearchTool, parameters)
    assert request.call_args.args == (
        "POST",
        "https://api.deepseek.com/v1/tools/search",
    )
    kwargs = request.call_args.kwargs
    assert kwargs["json"] == {**parameters, "count": 5}
    assert type(kwargs["json"]["count"]) is int
    assert kwargs["headers"]["Authorization"] == "Bearer test-secret"
    assert kwargs["timeout"] == (10, 90)
    assert messages[0].message.json_object == data
    assert json.loads(messages[1].message.text) == data


def test_search_defaults_and_empty_results():
    with patch("requests.request", return_value=_response({"results": []})) as request:
        messages = _invoke(DeepSeekSearchTool, {"query": "nothing"})
    assert request.call_args.kwargs["json"] == {
        "query": "nothing",
        "count": 10,
        "need_content": False,
    }
    assert messages[0].message.json_object == {"results": []}


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"query": " "},
        {"query": "字" * 129},
        {"query": 1},
        {"query": "x", "count": 0},
        {"query": "x", "count": 51},
        {"query": "x", "count": 1.5},
        {"query": "x", "count": True},
        {"query": "x", "count": float("nan")},
        {"query": "x", "count": "5"},
        {"query": "x", "need_content": "false"},
        {"query": "x", "ori_question": "x" * 129},
    ],
)
def test_invalid_search_input_does_not_make_a_request(parameters):
    with patch("requests.request") as request, pytest.raises((ValueError, TypeError)):
        _invoke(DeepSeekSearchTool, parameters)
    request.assert_not_called()


def test_fetch_request_and_markdown_output():
    data = {"title": "网页", "content": "# 内容\n\n正文"}
    with patch("requests.request", return_value=_response(data)) as request:
        messages = _invoke(DeepSeekFetchTool, {"url": "https://example.com/page"})
    assert request.call_args.args == ("POST", "https://api.deepseek.com/v1/tools/fetch")
    assert request.call_args.kwargs["json"] == {"url": "https://example.com/page"}
    assert messages[0].message.json_object == data
    assert messages[1].message.text == data["content"]


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "file:///local",
        "https:///missing",
        "https://user:pass@example.com",
        "https://example.com/with space",
        "https://[broken",
        "https://example.com/" + "x" * 8192,
    ],
)
def test_invalid_fetch_input_does_not_make_a_request(url):
    with patch("requests.request") as request, pytest.raises(ValueError):
        _invoke(DeepSeekFetchTool, {"url": url})
    request.assert_not_called()


@pytest.mark.parametrize(
    "status, expected",
    [
        (400, "parameters"),
        (401, "API key"),
        (402, "balance"),
        (403, "denied"),
        (404, "retrieve"),
        (429, "rate limit"),
        (500, "HTTP 500"),
    ],
)
def test_api_errors_do_not_echo_server_response_or_credentials(status, expected):
    with (
        patch(
            "requests.request", return_value=_response({"error": "test-secret"}, status)
        ),
        pytest.raises(ValueError, match=expected) as raised,
    ):
        _invoke(DeepSeekSearchTool, {"query": "x"})
    assert "test-secret" not in str(raised.value)


@pytest.mark.parametrize(
    "error", [requests.Timeout("test-secret"), requests.ConnectionError("test-secret")]
)
def test_network_errors_do_not_echo_credentials(error):
    with (
        patch("requests.request", side_effect=error),
        pytest.raises(ValueError) as raised,
    ):
        _invoke(DeepSeekFetchTool, {"url": "https://example.com"})
    assert "test-secret" not in str(raised.value)


@pytest.mark.parametrize("data", [[], {}, {"results": None}, {"results": ["invalid"]}])
def test_invalid_search_response_is_reported(data):
    with (
        patch("requests.request", return_value=_response(data)),
        pytest.raises(ValueError),
    ):
        _invoke(DeepSeekSearchTool, {"query": "x"})


def test_invalid_fetch_json_is_reported():
    response = _response(None)
    response.json.side_effect = ValueError("invalid JSON")
    with (
        patch("requests.request", return_value=response),
        pytest.raises(ValueError, match="JSON"),
    ):
        _invoke(DeepSeekFetchTool, {"url": "https://example.com"})


def test_provider_validation_avoids_paid_tool_calls():
    provider = object.__new__(DeepSeekProvider)
    with patch("requests.request", return_value=_response({"data": []})) as request:
        provider._validate_credentials({"api_key": "test-secret"})
    assert request.call_args.args == ("GET", "https://api.deepseek.com/models")
    with (
        patch("requests.request", return_value=_response({}, 401)),
        pytest.raises(ToolProviderCredentialValidationError, match="API key"),
    ):
        provider._validate_credentials({"api_key": "test-secret"})
    with (
        patch("requests.request") as request,
        pytest.raises(ToolProviderCredentialValidationError),
    ):
        provider._validate_credentials({})
    request.assert_not_called()


def test_sdk_loads_both_tools_and_icon_matches_model_plugin():
    plugin = PluginRegistration(DifyPluginEnv())
    assert plugin.configuration.name == "deepseek_tool"
    assert set(plugin.tools_mapping["deepseek"][2]) == {"search", "fetch"}
    assert not plugin.models_mapping
    assert (ROOT / "_assets/icon.svg").read_bytes() == (
        ROOT.parents[1] / "models/deepseek/_assets/icon.svg"
    ).read_bytes()
