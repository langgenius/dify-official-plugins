import json
from decimal import Decimal
from pathlib import Path

import anthropic
import httpx2
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import AssistantPromptMessage, UserPromptMessage

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel

MODEL = "claude-fable-5-2"
BLOCKS = [
    {"type": "thinking", "thinking": "", "signature": "signed-state"},
    {"type": "text", "text": "Checking."},
    {"type": "redacted_thinking", "data": "encrypted-state"},
    {"type": "tool_use", "id": "call_1", "name": "lookup", "input": {}},
]
USAGE = {
    "input_tokens": 10,
    "output_tokens": 3,
    "cache_creation_input_tokens": 2,
    "cache_read_input_tokens": 1,
    "cache_creation": {"ephemeral_5m_input_tokens": 1, "ephemeral_1h_input_tokens": 1},
    "speed": "fast",
}


@pytest.mark.parametrize("stream", [False, True])
def test_signed_blocks_replay_in_order_on_a_fresh_provider(monkeypatch, stream):
    schema = yaml.safe_load(
        (Path(__file__).parents[1] / "models/llm" / f"{MODEL}.yaml").read_text()
    )
    provider = AnthropicLargeLanguageModel([AIModelEntity(**schema)])
    message = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": BLOCKS,
        "stop_reason": "tool_use",
        "usage": USAGE,
    }

    def reply(request):
        assert json.loads(request.content)["speed"] == "fast"
        if not stream:
            return httpx2.Response(200, json=message)
        events = [
            {
                "type": "message_start",
                "message": {**message, "content": [], "stop_reason": None},
            }
        ]
        for index, block in enumerate(BLOCKS):
            events.extend(
                [
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": block,
                    },
                    {"type": "content_block_stop", "index": index},
                ]
            )
        events.extend(
            [
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use"},
                    "usage": {"output_tokens": 3},
                },
                {"type": "message_stop"},
            ]
        )
        body = "".join(
            f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
        )
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=body
        )

    with anthropic.Anthropic(
        api_key="test",
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(reply), trust_env=False
        ),
    ) as client:
        monkeypatch.setattr(llm_module, "Anthropic", lambda **_: client)
        chunks = list(
            provider.invoke(
                model=MODEL,
                credentials={"anthropic_api_key": "test"},
                prompt_messages=[UserPromptMessage(content="Check")],
                model_parameters={"max_tokens": 1000, "speed": "fast"},
                stream=stream,
            )
        )
    last = chunks[-1].delta
    fresh = AnthropicLargeLanguageModel([])
    replayed = fresh._process_assistant_message(last.message)["content"]
    assert replayed == BLOCKS
    assert (
        fresh._process_assistant_message(
            AssistantPromptMessage(content="Another chat")
        )["content"]
        != BLOCKS
    )
    assert last.usage.prompt_tokens == 13
    assert last.usage.prompt_price == Decimal("0.0002124")
    assert last.usage.completion_price == Decimal("0.000240")
