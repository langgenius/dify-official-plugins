import json
import os
import sys
from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    ToolPromptMessage,
    UserPromptMessage,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import DeepseekLargeLanguageModel

MODELS = tuple(yaml.safe_load((ROOT / "models" / "llm" / "_position.yaml").read_text()))
API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
LIVE_ENABLED = os.getenv("RUN_DEEPSEEK_LIVE") == "1"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (API_KEY and LIVE_ENABLED),
        reason="set RUN_DEEPSEEK_LIVE=1 and DEEPSEEK_API_KEY",
    ),
]


class _Credentials(dict[str, str]):
    def __repr__(self) -> str:
        return "DeepSeek live test credentials"

    __str__ = __repr__


schemas = [
    AIModelEntity.model_validate(
        yaml.safe_load((ROOT / "models" / "llm" / f"{model}.yaml").read_text())
    )
    for model in MODELS
]
llm = DeepseekLargeLanguageModel(model_schemas=schemas)


def _invoke(
    messages: list[PromptMessage],
    *,
    model: str = "deepseek-v4-flash",
    parameters: dict,
    tools: list[PromptMessageTool] | None = None,
    stream: bool,
) -> list[LLMResultChunk]:
    return list(
        llm.invoke(
            model=model,
            credentials=_Credentials(api_key=API_KEY),
            prompt_messages=messages,
            model_parameters=parameters,
            tools=tools,
            stream=stream,
            user="deepseek-live-test",
        )
    )


def _text(chunks: list[LLMResultChunk]) -> str:
    return "".join(
        chunk.delta.message.content
        for chunk in chunks
        if isinstance(chunk.delta.message.content, str)
    )


def _terminal(chunks: list[LLMResultChunk]):
    assert chunks
    terminal = chunks[-1].delta
    assert terminal.usage is not None
    assert terminal.usage.total_tokens > 0
    return terminal


@pytest.mark.parametrize("model", MODELS)
def test_every_current_model_accepts_a_minimal_request(model: str) -> None:
    chunks = _invoke(
        [UserPromptMessage(content="Reply only with OK.")],
        model=model,
        parameters={"thinking": False, "max_tokens": 16},
        stream=False,
    )

    assert _text(chunks).strip()
    _terminal(chunks)


@pytest.mark.parametrize(
    ("stream", "thinking", "effort", "max_tokens"),
    [
        pytest.param(False, None, None, 256, id="default-thinking-high-nonstream"),
        pytest.param(False, True, "low", 256, id="thinking-low-nonstream"),
        pytest.param(True, True, "max", 1024, id="thinking-max-stream"),
        pytest.param(True, False, "max", 32, id="nonthinking-stream"),
    ],
)
def test_thinking_modes_and_effort_boundaries(
    stream: bool,
    thinking: bool | None,
    effort: str | None,
    max_tokens: int,
) -> None:
    parameters = {"max_tokens": max_tokens}
    if thinking is not None:
        parameters["thinking"] = thinking
    if effort is not None:
        parameters["reasoning_effort"] = effort

    chunks = _invoke(
        [UserPromptMessage(content="Calculate 17 * 19, then reply only with 323.")],
        parameters=parameters,
        stream=stream,
    )

    text = _text(chunks)
    answer, reasoning = llm._extract_reasoning_content(text)
    assert "323" in answer
    assert text.count("<think>") == text.count("</think>")
    if thinking is False:
        assert reasoning is None
    else:
        assert reasoning
        if not stream:
            opaque_body = _terminal(chunks).message.opaque_body
            assert isinstance(opaque_body, dict)
            assert opaque_body["reasoning_content"] == reasoning
    _terminal(chunks)


def test_thinking_tool_call_replays_reasoning_content() -> None:
    tool = PromptMessageTool(
        name="get_live_test_marker",
        description="Return the marker required to finish the live test.",
        parameters={"type": "object", "properties": {}},
    )
    prompt = UserPromptMessage(
        content=(
            "Call get_live_test_marker exactly once before answering. "
            "Use its result and do not guess the marker."
        )
    )
    parameters = {
        "thinking": True,
        "reasoning_effort": "low",
        "max_tokens": 512,
    }

    messages: list[PromptMessage] = [prompt]
    for sub_turn in range(3):
        chunks = _invoke(
            messages,
            parameters=parameters,
            tools=[tool],
            stream=False,
        )
        assistant = _terminal(chunks).message
        if not assistant.tool_calls:
            break

        assert isinstance(assistant.opaque_body, dict)
        assert assistant.opaque_body["reasoning_content"]
        assert all(call.id for call in assistant.tool_calls)
        assert all(call.function.name == tool.name for call in assistant.tool_calls)
        messages.extend(
            [
                assistant,
                *[
                    ToolPromptMessage(
                        content='{"marker":"LIVE_TOOL_OK"}',
                        tool_call_id=call.id,
                    )
                    for call in assistant.tool_calls
                ],
            ]
        )
    else:
        pytest.fail("tool loop did not finish within three sub-turns")

    assert sub_turn > 0
    answer, _ = llm._extract_reasoning_content(_text(chunks))
    assert "LIVE_TOOL_OK" in answer


def test_json_object_output() -> None:
    chunks = _invoke(
        [
            UserPromptMessage(
                content=(
                    'Return only a JSON object matching this example: {"answer":"OK"}. '
                    'Use exactly the JSON key "answer" and value "OK".'
                )
            )
        ],
        parameters={
            "thinking": False,
            "max_tokens": 64,
            "response_format": "json_object",
        },
        stream=False,
    )

    content = _text(chunks)
    if not content.strip():
        pytest.xfail("DeepSeek documents occasional empty JSON Object responses")
    result = json.loads(content)
    assert isinstance(result, dict)
    assert "answer" in result
    _terminal(chunks)
