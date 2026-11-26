from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dify_plugin.entities.tool import ToolRuntime
from openai import OpenAI
from tools.dalle2 import DallE2Tool
from tools.dalle3 import DallE3Tool
from tools.deep_research import DeepResearchTool


@pytest.mark.parametrize(
    ("endpoint", "expected_model", "expected_search"),
    [
        ("https://api.openai.com/v1", "gpt-5.6-sol", "web_search"),
        ("https://api.example.com/v1", "o4-mini-deep-research", "web_search_preview"),
    ],
)
def test_research_start_with_saved_model(endpoint, expected_model, expected_search):
    response = SimpleNamespace(id="response-1")
    create = MagicMock(return_value=response)
    client = SimpleNamespace(
        base_url=OpenAI(api_key="test", base_url=endpoint).base_url,
        responses=SimpleNamespace(create=create),
    )
    tool = DeepResearchTool(runtime=None, session=None)

    list(
        tool._handle_start(
            client,
            {
                "model": "o4-mini-deep-research",
                "prompt": "Research query",
                "temperature": 0.5,
            },
        )
    )

    args = create.call_args.kwargs
    assert args["model"] == expected_model
    assert args["background"] is True
    assert args["tools"][0]["type"] == expected_search
    assert ("temperature" in args) == (expected_search == "web_search_preview")


@pytest.mark.parametrize(
    ("tool_class", "module", "model"),
    [
        (DallE2Tool, "tools.dalle2", "dall-e-2"),
        (DallE3Tool, "tools.dalle3", "dall-e-3"),
    ],
)
def test_dalle_remains_available_with_compatible_endpoint(
    tool_class, module, model, monkeypatch
):
    runtime = ToolRuntime(
        user_id="test", session_id=None, credentials={"openai_api_key": "test"}
    )
    tool = tool_class(runtime=runtime, session=None)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="OpenAI retired DALL-E"):
        list(tool._invoke({"prompt": "test"}))

    generate = MagicMock(return_value=SimpleNamespace(data=[]))
    client = SimpleNamespace(
        base_url=OpenAI(api_key="test", base_url="https://api.example.com").base_url,
        images=SimpleNamespace(generate=generate),
    )
    monkeypatch.setattr(f"{module}.OpenAI", lambda **kwargs: client)
    list(tool._invoke({"prompt": "test"}))
    assert generate.call_args.kwargs["model"] == model
