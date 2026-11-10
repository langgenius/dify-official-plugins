"""GPT OSS on Converse must receive tools.

openai.yaml advertises tool-call / stream-tool-call, and Converse accepts
toolConfig for openai.gpt-oss-*, so the capability entry for the
"openai.gpt" prefix has to allow tool use. No network: the bedrock client
is mocked and stops the call once the request has been built.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest

llm_mod = importlib.import_module("models.llm.llm")
BedrockLLM = llm_mod.BedrockLargeLanguageModel

TOOL = llm_mod.PromptMessageTool(
    name="get_weather",
    description="Get current weather for one city",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)


@pytest.mark.parametrize("model_id", ["openai.gpt-oss-120b-1:0", "openai.gpt-oss-20b-1:0"])
def test_gpt_oss_converse_request_carries_tool_config(model_id: str) -> None:
    model_info = BedrockLLM._find_model_info(model_id)
    client = MagicMock(name="bedrock_client")
    client.converse.side_effect = NameError("request built")
    with patch.object(llm_mod, "get_bedrock_client", return_value=client), pytest.raises(NameError):
        object.__new__(BedrockLLM)._generate_with_converse(
            model_info={**model_info, "model": model_id},
            credentials={"aws_region": "us-east-1"},
            prompt_messages=[llm_mod.UserPromptMessage(content="Weather in Paris?")],
            model_parameters={},
            stream=False,
            tools=[TOOL],
        )
    tool_config = client.converse.call_args.kwargs["toolConfig"]
    assert [t["toolSpec"]["name"] for t in tool_config["tools"]] == ["get_weather"]
