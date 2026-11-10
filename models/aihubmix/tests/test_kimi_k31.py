import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import AssistantPromptMessage, ToolPromptMessage, UserPromptMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from models.llm.llm import AihubmixLargeLanguageModel


@pytest.mark.parametrize("model", ['kimi-k3.1-pro', 'kimi-k3.1-pro-highspeed'])
@pytest.mark.parametrize("effort", ["low", "high", "max"])
def test_kimi_request_preserves_reasoning_and_parameters(model, effort):
    schema = AIModelEntity.model_validate(yaml.safe_load(
        (ROOT / "models" / "llm" / f"{model}.yaml").read_text()
    ))
    llm = AihubmixLargeLanguageModel([schema])
    reasoning = "  keep exact reasoning\n"
    tool_call = AssistantPromptMessage.ToolCall(
        id="call_1", type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(name="lookup", arguments="{}"),
    )
    response = Mock(status_code=200, encoding="utf-8")
    response.json.return_value = {
        "id": "chatcmpl-test", "model": model,
        "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "done", "reasoning_content": reasoning,
        }}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    with patch("dify_plugin.interfaces.model.openai_compatible.llm.requests.post", return_value=response) as post:
        chunks = list(llm.invoke(
            model=model, credentials={"api_key": "test-key"},
            prompt_messages=[
                UserPromptMessage(content="Look up the answer."),
                AssistantPromptMessage(content=f"<think>{reasoning}</think>", tool_calls=[tool_call]),
                ToolPromptMessage(tool_call_id="call_1", content="42"),
            ],
            model_parameters={"max_tokens": 128, "reasoning_effort": effort}, stream=False,
        ))
    body = json.loads(post.call_args.kwargs["data"])
    assert body["model"] == model
    assert body["reasoning_effort"] == effort
    assert body['max_completion_tokens'] == 128
    assert not {"thinking", "temperature", "top_p"}.intersection(body)
    assistant = body["messages"][1]
    assert assistant["content"] == ""
    assert assistant["reasoning_content"] == reasoning
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert chunks[0].delta.message.content == f"<think>{reasoning}</think>done"


def test_kimi_adapter_leaves_other_models_unchanged():
    llm = AihubmixLargeLanguageModel([])
    message = AssistantPromptMessage(content="<think>literal text</think>answer")
    assert llm._convert_prompt_message_to_dict(message, {"_kimi_k31": False}) == {
        "role": "assistant", "content": message.content,
    }
