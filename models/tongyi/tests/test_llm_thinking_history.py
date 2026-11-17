"""在 DashScope 调用边界验证历史思考协议，不清洗供应商响应。"""

import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResult, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dashscope.api_entities.dashscope_response import (
    GenerationOutput,
    GenerationResponse,
    GenerationUsage,
)

from models.llm.llm import TongyiLargeLanguageModel


HISTORY = "<think>\n历史思考\n</think>正式回答"
TOOL_CALLS = [
    {
        "id": "call_weather_1",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": '{"city": "杭州", "example": "<think>\\n参数\\n</think>"}',
        },
    },
    {
        "id": "call_weather_2",
        "type": "function",
        "function": {"name": "get_weather", "arguments": '{"city":"上海"}'},
    },
]


def _response(content="", *, reasoning_content="", finish_reason=None):
    return GenerationResponse(
        status_code=200,
        output=GenerationOutput(
            choices=[
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "reasoning_content": reasoning_content,
                    },
                    "finish_reason": finish_reason,
                }
            ]
        ),
        usage=GenerationUsage(input_tokens=10, output_tokens=5),
    )


@pytest.fixture(params=[False, True], ids=["generation", "multimodal"])
def invoke(request, monkeypatch):
    """仅替换远端 SDK 调用及计价，执行真实参数、历史和响应转换。"""
    vision = request.param
    calls = []

    def sdk_call(api, **kwargs):
        calls.append({**kwargs, "messages": deepcopy(kwargs["messages"]), "api": api})
        content = [{"text": "本轮正式回答"}] if vision else "本轮正式回答"
        if kwargs["stream"]:
            return iter(
                [
                    _response(reasoning_content="本轮思考"),
                    _response(content),
                    _response(finish_reason="stop"),
                ]
            )
        return _response(content, finish_reason="stop")

    monkeypatch.setattr(
        "models.llm.llm.Generation.call", lambda **kwargs: sdk_call("generation", **kwargs)
    )
    monkeypatch.setattr(
        "models.llm.llm.MultiModalConversation.call",
        lambda **kwargs: sdk_call("multimodal", **kwargs),
    )

    def run(messages, parameters=None, *, model_name="qwen3.8-max", stream=False, tools=None):
        model = TongyiLargeLanguageModel(model_schemas=MagicMock())
        model.get_model_mode = MagicMock(return_value="chat")
        model.get_model_schema = MagicMock(
            return_value=SimpleNamespace(features=[ModelFeature.VISION] if vision else [])
        )
        model._calc_response_usage = MagicMock(return_value=LLMUsage.empty_usage())
        result = model._generate(
            model=model_name,
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=messages,
            model_parameters=dict(parameters or {}),
            tools=tools,
            stream=stream,
        )
        if not isinstance(result, LLMResult):
            result = list(result)
        assert calls[-1]["api"] == ("multimodal" if vision else "generation")
        return calls[-1], result

    return run


def _content(call, text):
    return [{"text": text}] if call["api"] == "multimodal" else text


@pytest.mark.parametrize(
    "parameters,thinking",
    [
        ({}, True),
        ({"enable_thinking": True}, True),
        ({"enable_thinking": False}, False),
        ({"enable_thinking": False, "preserve_thinking": True}, False),
        ({"preserve_thinking": True}, True),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
def test_history_policy_uses_normalized_parameters(invoke, parameters, thinking, stream):
    messages = [AssistantPromptMessage(content=HISTORY), UserPromptMessage(content="继续")]
    call, _ = invoke(messages, parameters, stream=stream)

    assert call["preserve_thinking"] is False
    assert call["enable_thinking"] is thinking
    assert call["messages"][0] == {"role": "assistant", "content": _content(call, "正式回答")}
    assert messages[0].content == HISTORY


@pytest.mark.parametrize(
    "content,expected",
    [
        (HISTORY, "正式回答"),
        ("开场<think>\n思考一\n</think>正文一<think>\n思考二\n</think>正文二", "开场正文一正文二"),
        ("<think>\n一\n</think><think>\n二\n</think>结尾", "结尾"),
        (" \n<think>\n思考\n</think>  正文\n", " \n  正文\n"),
        ("<think>\n<!--dify-deepseek-reasoning-->旧思考\n</think>正文", "正文"),
        ("<think>\n\n</think>正文", "正文"),
        ("<think>\n只有思考\n</think>", " "),
        # 没有来源标记，完全相同的正文示例也按历史协议块处理。
        ("格式示例：```\n<think>\n示例\n</think>\n```", "格式示例：```\n\n```"),
    ],
)
def test_complete_protocol_blocks_are_removed_without_trimming_body(invoke, content, expected):
    call, _ = invoke([AssistantPromptMessage(content=content)])
    assert call["messages"] == [{"role": "assistant", "content": _content(call, expected)}]


@pytest.mark.parametrize(
    "content",
    [
        "普通助手正文，保留所有空白。 \n",
        "请解释 <think> 和 </think> 标签。",
        "<think>这是行内示例</think>正文",
        "<think>\n未闭合的历史及正文",
        "<think>\n只有半个关闭标签</thin",
        "孤立的 </think> 及其前后正文",
        "</think>正式回答",
        "<think>\n缺少关闭前换行</think>正文",
        "<think>缺少开启后换行\n</think>正文",
        "<THINK>\n大小写不同的标签\n</THINK>",
        "<think>\r\n非协议换行\r\n</think>",
        "<think source='example'>\n带属性的标签\n</think>",
        "&lt;think&gt;\n转义示例\n&lt;/think&gt;",
    ],
)
def test_non_protocol_and_incomplete_tag_text_is_unchanged(invoke, content):
    call, _ = invoke([AssistantPromptMessage(content=content)])
    assert call["messages"][0]["content"] == _content(call, content)


def test_incomplete_block_does_not_consume_body_before_a_complete_block(invoke):
    prefix = "<think>\n缺少协议换行</think>需要保留的正文"
    call, _ = invoke([AssistantPromptMessage(content=prefix + HISTORY)])
    assert call["messages"][0]["content"] == _content(call, prefix + "正式回答")


@pytest.mark.parametrize(
    "content,expected",
    [(HISTORY, "正式回答"), ("<think>\n调用前思考\n</think>", " "), ("", " "), (None, " ")],
)
def test_tool_calls_and_associated_results_are_preserved(invoke, content, expected):
    assistant = AssistantPromptMessage(content=content, tool_calls=deepcopy(TOOL_CALLS))
    messages = [
        UserPromptMessage(content="查询天气"),
        assistant,
        ToolPromptMessage(content="<think>\n工具结果一\n</think>", tool_call_id="call_weather_1"),
        ToolPromptMessage(content="工具结果二", tool_call_id="call_weather_2"),
    ]
    original = deepcopy(messages)
    tools = [
        PromptMessageTool(
            name="get_weather",
            description="查询天气",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        )
    ]
    call, _ = invoke(messages, tools=tools)

    assert len(call["messages"]) == len(messages)
    assert call["messages"][1] == {
        "role": "assistant",
        "content": _content(call, expected),
        "tool_calls": TOOL_CALLS,
    }
    # 关联结果保留现有 Tongyi 的 name 映射，不在本次修改工具协议。
    assert call["messages"][2:] == [
        {"role": "tool", "content": message.content, "name": message.tool_call_id}
        for message in messages[2:]
    ]
    assert call["tools"][0]["function"]["name"] == "get_weather"
    assert messages == original
    assert messages[1] is assistant


def test_other_roles_are_not_processed(invoke):
    messages = [
        SystemPromptMessage(content=HISTORY),
        UserPromptMessage(content=HISTORY),
        AssistantPromptMessage(content=HISTORY),
        ToolPromptMessage(content=HISTORY, tool_call_id="call_1"),
    ]
    original = deepcopy(messages)
    call, _ = invoke(messages)

    assert call["messages"] == [
        {"role": "system", "content": _content(call, HISTORY)},
        {"role": "user", "content": _content(call, HISTORY)},
        {"role": "assistant", "content": _content(call, "正式回答")},
        {"role": "tool", "content": HISTORY, "name": "call_1"},
    ]
    assert messages == original


@pytest.mark.parametrize(
    "model_name", ["qwen3.8-flash", "qwen3.7-max", "qwen-plus", "deepseek-v3.2"]
)
@pytest.mark.parametrize(
    "parameters",
    [{}, {"preserve_thinking": False}, {"enable_thinking": True, "preserve_thinking": False}],
)
def test_non_target_models_keep_existing_history_behavior(invoke, model_name, parameters):
    messages = [AssistantPromptMessage(content=HISTORY, tool_calls=deepcopy(TOOL_CALLS))]
    call, _ = invoke(messages, parameters, model_name=model_name)
    assert call["messages"] == [
        {"role": "assistant", "content": _content(call, HISTORY), "tool_calls": TOOL_CALLS}
    ]


def test_outbound_copy_keeps_internal_history_and_current_reasoning_output(invoke):
    messages = [AssistantPromptMessage(content=HISTORY), UserPromptMessage(content="继续")]
    original = deepcopy(messages)
    call, result = invoke(messages)

    assert call["messages"][0]["content"] == _content(call, "正式回答")
    assert "".join(chunk.delta.message.content for chunk in result) == (
        "<think>\n本轮思考\n</think>本轮正式回答"
    )
    assert messages == original
    # 在同一份历史上调用其他模型，仍应看到未修改的原文。
    other_call, _ = invoke(messages, model_name="qwen-plus")
    assert other_call["messages"][0]["content"] == _content(other_call, HISTORY)


def test_conversion_without_explicit_policy_is_unchanged():
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    assert model._convert_prompt_messages_to_tongyi_messages(
        [AssistantPromptMessage(content=HISTORY)]
    ) == [{"role": "assistant", "content": HISTORY}]


@pytest.mark.skipif(
    os.getenv("RUN_TONGYI_THINKING_HISTORY_LIVE") != "1" or not os.getenv("DASHSCOPE_API_KEY"),
    reason="需显式启用 RUN_TONGYI_THINKING_HISTORY_LIVE=1 并配置 DASHSCOPE_API_KEY",
)
@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("with_history", [False, True], ids=["fresh", "history"])
def test_live_qwen38_tool_round_trip(monkeypatch, thinking, with_history):
    """可选真实接口对照；仅使用合成上下文与本地无副作用的工具结果。"""
    import json

    import yaml
    from dashscope import MultiModalConversation
    from gevent import Timeout

    schema = AIModelEntity.model_validate(
        yaml.safe_load(
            (Path(__file__).parents[1] / "models/llm/qwen3.8-max.yaml").read_text()
        )
    )
    model = TongyiLargeLanguageModel(model_schemas=[schema])
    messages = [
        SystemPromptMessage(
            content="Call get_test_marker exactly once, then answer with the returned marker only."
        )
    ]
    if with_history:
        messages.extend(
            [
                UserPromptMessage(content="确认准备完毕"),
                AssistantPromptMessage(content="<think>\n历史思考哨兵\n</think>准备完毕"),
            ]
        )
    messages.append(UserPromptMessage(content="Get the test marker now."))
    tools = [
        PromptMessageTool(
            name="get_test_marker",
            description="Get the marker required to answer the user.",
            parameters={"type": "object", "properties": {}},
        )
    ]
    captured = []
    sdk_call = MultiModalConversation.call

    def record_call(**kwargs):
        captured.append(deepcopy(kwargs["messages"]))
        assert kwargs["preserve_thinking"] is False
        assert kwargs["enable_thinking"] is thinking
        return sdk_call(**kwargs)

    monkeypatch.setattr(MultiModalConversation, "call", record_call)

    def run_turn():
        snapshot = deepcopy(messages)
        parameters = {"enable_thinking": thinking, "max_completion_tokens": 4096}
        if thinking:
            parameters["reasoning_effort"] = "low"
        with Timeout(90):
            chunks = list(
                model._generate(
                    model="qwen3.8-max",
                    credentials={"dashscope_api_key": os.environ["DASHSCOPE_API_KEY"]},
                    prompt_messages=messages,
                    model_parameters=parameters,
                    tools=tools,
                    stream=True,
                )
            )
        assert messages == snapshot
        assert "历史思考哨兵" not in json.dumps(captured[-1], ensure_ascii=False)
        return AssistantPromptMessage(
            content="".join(chunk.delta.message.content or "" for chunk in chunks),
            tool_calls=[tool for chunk in chunks for tool in chunk.delta.message.tool_calls],
        )

    assistant = run_turn()
    assert len(assistant.tool_calls) == 1
    tool_call = assistant.tool_calls[0]
    assert tool_call.function.name == "get_test_marker"
    assert json.loads(tool_call.function.arguments) == {}
    if thinking:
        assert "<think>\n" in assistant.content and "\n</think>" in assistant.content
    messages.extend(
        [
            assistant,
            ToolPromptMessage(content="MARKER_44964_OK", tool_call_id=tool_call.id),
        ]
    )
    final = run_turn()
    assert not final.tool_calls
    assert "MARKER_44964_OK" in final.content
    replay = captured[-1][-2]
    assert replay["tool_calls"] == [tool_call.model_dump()]
    assert "<think>" not in json.dumps(replay["content"])
    assert captured[-1][-1]["content"] == "MARKER_44964_OK"
