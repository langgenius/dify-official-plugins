from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import AssistantPromptMessage, ToolPromptMessage, UserPromptMessage

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel


@pytest.mark.parametrize(
    "threshold,cache_tools,ttl",
    [(3, True, "1h"), (3, False, "5m"), (0, True, "1h"), (0, False, "5m")],
)
def test_signed_replay_applies_current_cache_policy_and_prunes_breakpoints(
    monkeypatch, threshold, cache_tools, ttl
):
    schema = AIModelEntity.model_validate(yaml.safe_load(
        (Path(__file__).parents[1] / "models/llm/claude-opus-5-5.yaml").read_text()
    ))
    llm = AnthropicLargeLanguageModel(model_schemas=[schema])
    blocks = [
        {"type": "thinking", "thinking": "", "signature": "signed-prefix"},
        {"type": "text", "text": "short"},
        {"type": "text", "text": "three word reply"},
        {"type": "tool_use", "id": "tool", "name": "lookup", "input": {"q": "a"}},
        {"type": "redacted_thinking", "data": "encrypted"},
        *[{"type": "text", "text": "word " * length} for length in range(4, 8)],
    ]
    assistant = AssistantPromptMessage(content="display text", opaque_body={"anthropic_content": blocks})
    history = [UserPromptMessage(content="lookup"), assistant, ToolPromptMessage(content="found", tool_call_id="tool")]
    llm._message_flow_cache_threshold = threshold
    llm._tool_results_cache_enabled = cache_tools
    llm._prompt_cache_ttl = ttl
    _, messages = llm._convert_prompt_messages(history)
    replay = messages[1]["content"]
    expected_cached = {2, 5, 6, 7, 8} if threshold else set()
    if cache_tools:
        expected_cached.add(3)
    assert {i for i, block in enumerate(replay) if "cache_control" in block} == expected_cached
    assert all(block["cache_control"] == {"type": "ephemeral", "ttl": ttl} for block in replay if "cache_control" in block)

    calls = []
    monkeypatch.setattr(llm_module, "Anthropic", lambda **kwargs: SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs))
    ))
    llm._chat_generate(
        model=schema.model,
        credentials={"anthropic_api_key": "test"},
        prompt_messages=history,
        model_parameters={
            "max_tokens": 1024,
            "prompt_caching_message_flow": threshold,
            "prompt_caching_tool_results": cache_tools,
            "prompt_caching_ttl": ttl,
        },
    )
    request_blocks = [block for message in calls[0]["messages"] if isinstance(message["content"], list) for block in message["content"]]
    assert sum("cache_control" in block for block in request_blocks) == min(4, len(expected_cached) + cache_tools)
    for replay in (replay, calls[0]["messages"][1]["content"]):
        assert [{key: value for key, value in block.items() if key != "cache_control"} for block in replay] == blocks
    assert assistant.opaque_body == {"anthropic_content": blocks}
    assert all("cache_control" not in block for block in blocks)
