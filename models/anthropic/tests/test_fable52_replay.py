import json
import logging
from decimal import Decimal
from pathlib import Path

import anthropic
import httpx2
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel

MODEL = "claude-fable-5-2"
BLOCKS = [
    {"type": "thinking", "thinking": "", "signature": "signed-state"},
    {"type": "thinking", "thinking": "Visible summary.", "signature": "signed-summary"},
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
def test_signed_blocks_replay_in_order_on_a_fresh_provider(monkeypatch, caplog, stream):
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

    requests = []

    def reply(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["speed"] == "fast"
        if not body["stream"]:
            return httpx2.Response(200, json=message)
        events = [
            {
                "type": "message_start",
                "message": {**message, "content": [], "stop_reason": None},
            }
        ]
        for index, block in enumerate(BLOCKS):
            start = dict(block)
            deltas = []
            if block["type"] == "thinking":
                start.update(thinking="", signature="")
                deltas = [
                    {"type": "thinking_delta", "thinking": block["thinking"]},
                    {"type": "signature_delta", "signature": block["signature"]},
                ]
            elif block["type"] == "text":
                start["text"] = ""
                deltas = [
                    {"type": "text_delta", "text": text} for text in ("Check", "ing.")
                ]
            events.append(
                {"type": "content_block_start", "index": index, "content_block": start}
            )
            for delta in deltas:
                events.append(
                    {"type": "content_block_delta", "index": index, "delta": delta}
                )
            events.append({"type": "content_block_stop", "index": index})
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
        if stream:
            caplog.set_level(logging.DEBUG)
        prompt = UserPromptMessage(content="Check")
        chunks = list(
            provider.invoke(
                model=MODEL,
                credentials={"anthropic_api_key": "test"},
                prompt_messages=[prompt],
                model_parameters={"max_tokens": 1000, "speed": "fast"},
                stream=stream,
            )
        )
        last = chunks[-1].delta
        assert (
            "".join(chunk.delta.message.content for chunk in chunks)
            == "<think>\nVisible summary.\n</think>\n\nChecking."
        )
        next_provider = AnthropicLargeLanguageModel([AIModelEntity(**schema)])
        list(
            next_provider.invoke(
                model=MODEL,
                credentials={"anthropic_api_key": "test"},
                prompt_messages=[
                    prompt,
                    last.message,
                    ToolPromptMessage(tool_call_id="call_1", content="Result"),
                ],
                model_parameters={
                    "max_tokens": 1000,
                    "speed": "fast",
                    "prompt_caching_message_flow": 1,
                    "prompt_caching_tool_results": True,
                    "prompt_caching_ttl": "1h",
                },
                stream=False,
            )
        )
    cache = {"type": "ephemeral", "ttl": "1h"}
    assert requests[-1]["messages"][1]["content"] == [
        {**block, "cache_control": cache}
        if block["type"] in {"text", "tool_use"}
        else block
        for block in BLOCKS
    ]
    assert last.message.opaque_body == {"anthropic_content": BLOCKS}
    if stream:
        prefix = "Anthropic API Stream Response Chunk: "
        logged = [
            json.loads(record.message.removeprefix(prefix))
            for record in caplog.records
            if record.message.startswith(prefix)
        ]
        assert any(event["type"] == "content_block_delta" for event in logged)
        assert all(
            set(event) == {"type", "index"}
            for event in logged
            if event["type"] == "content_block_stop"
        )
        assert all("snapshot" not in event for event in logged)
        assert logged[-1] == {"type": "message_stop"}
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
