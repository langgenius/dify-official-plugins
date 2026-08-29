"""
Offline tests for the streaming response handler, driven by synthetic chunks.

These cover the paths a live test against a well-behaved endpoint cannot reach: a stream that
ends without a finish_reason, reasoning models whose visible content arrives late, and usage
riding on the finish chunk rather than a trailing empty one. They run in CI with no credentials.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import DeepInfraLargeLanguageModel  # noqa: E402

MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"


def _schemas() -> list[AIModelEntity]:
    directory = ROOT / "models" / "llm"
    return [
        AIModelEntity.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in directory.glob("*.yaml")
        if path.name != "_position.yaml"
    ]


@pytest.fixture
def llm() -> DeepInfraLargeLanguageModel:
    return DeepInfraLargeLanguageModel(model_schemas=_schemas())


def _tool_call_delta(index: int, *, call_id: str = "", name: str = "", arguments: str = ""):
    return SimpleNamespace(
        index=index,
        id=call_id,
        type="function" if name else None,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _delta(content=None, tool_calls=None, reasoning_content=None):
    payload = {"content": content, "tool_calls": tool_calls, "reasoning_content": reasoning_content}
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
        model_dump=lambda: payload,
    )


def _chunk(*, delta=None, finish_reason=None, usage=None, index=0):
    choices = (
        []
        if delta is None
        else [SimpleNamespace(index=index, delta=delta, finish_reason=finish_reason)]
    )
    return SimpleNamespace(model=MODEL, system_fingerprint=None, choices=choices, usage=usage)


def _run(llm, chunks):
    return list(
        llm._handle_chat_generate_stream_response(
            model=MODEL,
            credentials={"api_key": "unused-offline"},
            response=iter(chunks),
            prompt_messages=[UserPromptMessage(content="hi")],
            tools=None,
        )
    )


def _tool_calls(chunks):
    return [call for chunk in chunks for call in (chunk.delta.message.tool_calls or [])]


def _text(chunks) -> str:
    return "".join(c.delta.message.content or "" for c in chunks)


def test_tool_call_survives_a_stream_that_never_sends_finish_reason(llm) -> None:
    """
    Draining the buffer only on finish_reason loses a fully reassembled call with no error at
    all, which is the worst possible failure mode for an agent.
    """
    chunks = _run(
        llm,
        [
            _chunk(delta=_delta(tool_calls=[_tool_call_delta(0, call_id="call_1", name="get_weather")])),
            _chunk(delta=_delta(tool_calls=[_tool_call_delta(0, arguments='{"city":')])),
            _chunk(delta=_delta(tool_calls=[_tool_call_delta(0, arguments='"Tokyo"}')])),
        ],
    )

    calls = _tool_calls(chunks)
    assert len(calls) == 1
    assert calls[0].function.name == "get_weather"
    assert calls[0].function.arguments == '{"city":"Tokyo"}'
    assert calls[0].id == "call_1"


def test_parallel_tool_calls_reassemble_independently(llm) -> None:
    chunks = _run(
        llm,
        [
            _chunk(delta=_delta(tool_calls=[_tool_call_delta(0, call_id="a", name="first")])),
            _chunk(delta=_delta(tool_calls=[_tool_call_delta(1, call_id="b", name="second")])),
            _chunk(delta=_delta(tool_calls=[_tool_call_delta(1, arguments='{"x":2}')])),
            _chunk(delta=_delta(tool_calls=[_tool_call_delta(0, arguments='{"x":1}')])),
            _chunk(delta=_delta(content=""), finish_reason="tool_calls"),
        ],
    )

    calls = _tool_calls(chunks)
    assert [c.function.name for c in calls] == ["first", "second"]
    assert [c.function.arguments for c in calls] == ['{"x":1}', '{"x":2}']


def test_reasoning_content_is_surfaced_as_think_block(llm) -> None:
    """Reasoning models stream thinking before any content; dropping it leaves a silent gap."""
    chunks = _run(
        llm,
        [
            _chunk(delta=_delta(reasoning_content="weighing options")),
            _chunk(delta=_delta(reasoning_content=" some more")),
            _chunk(delta=_delta(content="OK"), finish_reason="stop"),
        ],
    )

    text = _text(chunks)
    assert "weighing options" in text
    assert "<think>" in text and "</think>" in text
    assert text.rstrip().endswith("OK")


def test_usage_on_the_finish_chunk_is_used(llm) -> None:
    """
    Reading usage only from a choices-empty chunk silently falls back to the GPT-2 estimate,
    which is the wrong vocabulary for every model DeepInfra serves.
    """
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)
    chunks = _run(
        llm,
        [
            _chunk(delta=_delta(content="hello")),
            _chunk(delta=_delta(content=""), finish_reason="stop", usage=usage),
        ],
    )

    reported = chunks[-1].delta.usage
    assert reported.prompt_tokens == 11
    assert reported.completion_tokens == 7


def test_usage_on_a_trailing_empty_chunk_is_still_used(llm) -> None:
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=5)
    chunks = _run(
        llm,
        [
            _chunk(delta=_delta(content="hello"), finish_reason="stop"),
            _chunk(usage=usage),
        ],
    )

    reported = chunks[-1].delta.usage
    assert reported.prompt_tokens == 3
    assert reported.completion_tokens == 5


def test_tool_call_arguments_are_counted(llm) -> None:
    """
    The tool_calls branch of the token counter was unreachable: a list value was flattened to ""
    before the key was tested, so tool payloads counted as zero.
    """
    from dify_plugin.entities.model.message import AssistantPromptMessage

    call = AssistantPromptMessage.ToolCall(
        id="call_1",
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name="get_weather", arguments='{"city":"Tokyo","unit":"celsius"}'
        ),
    )
    with_call = AssistantPromptMessage(content="", tool_calls=[call])
    without_call = AssistantPromptMessage(content="", tool_calls=[])

    assert llm._num_tokens_from_messages(MODEL, [with_call]) > llm._num_tokens_from_messages(
        MODEL, [without_call]
    )
