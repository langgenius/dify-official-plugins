import json
from pathlib import Path

import anthropic
import httpx2
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel

MODEL = "claude-sonnet-5-5"


def _send(monkeypatch, prompt_messages, tools, model_parameters):
    schema = yaml.safe_load(
        (Path(__file__).parents[1] / "models/llm" / f"{MODEL}.yaml").read_text(encoding="utf-8")
    )
    provider = AnthropicLargeLanguageModel([AIModelEntity(**schema)])
    requests = []

    def reply(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [{"type": "text", "text": "Done."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    with anthropic.Anthropic(
        api_key="test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(reply), trust_env=False),
    ) as client:
        monkeypatch.setattr(llm_module, "Anthropic", lambda **_: client)
        list(
            provider.invoke(
                model=MODEL,
                credentials={"anthropic_api_key": "test"},
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stream=False,
            )
        )
    return requests[-1]


def _marked(body):
    """Every block that carries cache_control, in render order (tools, system, messages)."""
    marked = [("tool", t["name"]) for t in body.get("tools", []) if "cache_control" in t]
    system = body.get("system")
    if isinstance(system, list):
        marked += [("system", b["text"]) for b in system if "cache_control" in b]
    for index, message in enumerate(body["messages"]):
        if isinstance(message["content"], list):
            marked += [(index, b["type"]) for b in message["content"] if "cache_control" in b]
    return marked


def test_tool_loop_keeps_cache_marker_on_newest_tool_result(monkeypatch):
    # An agent loop that has run several tool rounds: every tool_use/tool_result is a
    # cache candidate, more than the 4 breakpoints Anthropic allows.
    messages = [SystemPromptMessage(content="You are a helper."), UserPromptMessage(content="Go")]
    for round_ in range(5):
        messages.append(
            AssistantPromptMessage(
                content="",
                tool_calls=[
                    AssistantPromptMessage.ToolCall(
                        id=f"call_{round_}",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="lookup", arguments="{}"
                        ),
                    )
                ],
            )
        )
        messages.append(ToolPromptMessage(tool_call_id=f"call_{round_}", content=f"result {round_}"))
    tools = [PromptMessageTool(name="lookup", description="Look up.", parameters={"type": "object", "properties": {}})]

    body = _send(
        monkeypatch,
        messages,
        tools,
        {
            "max_tokens": 1000,
            "prompt_caching_tool_definitions": True,
            "prompt_caching_tool_results": True,
        },
    )

    marked = _marked(body)
    assert len(marked) <= 4
    # Prompt caching is a prefix match: only a breakpoint at the end of the request
    # lets the next turn read everything sent so far. The newest tool_result must keep it.
    last = len(body["messages"]) - 1
    assert body["messages"][last]["content"][-1]["type"] == "tool_result"
    assert (last, "tool_result") in marked
