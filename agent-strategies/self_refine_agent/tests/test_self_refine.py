import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.core.runtime import Session
from dify_plugin.core.server.stdio.request_reader import StdioRequestReader
from dify_plugin.core.server.stdio.response_writer import StdioResponseWriter
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import AIModelEntity, ModelFeature, ModelType
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    TextPromptMessageContent,
    ToolPromptMessage,
    ensure_prompt_message,
)
from dify_plugin.entities.tool import (
    ToolDescription,
    ToolInvokeMessage,
    ToolParameter,
    ToolProviderType,
)
from dify_plugin.interfaces.agent import (
    AgentModelConfig,
    AgentToolIdentity,
    ToolEntity,
)

from strategies.self_refine import SelfRefineParams, SelfRefineStrategy


def _list_content_message(text: str) -> AssistantPromptMessage:
    return AssistantPromptMessage(content=[TextPromptMessageContent(data=text)])


def _tool_entity() -> ToolEntity:
    return ToolEntity(
        identity=AgentToolIdentity(
            author="tester",
            name="search",
            label=I18nObject(en_US="Search"),
            provider="tavily",
        ),
        parameters=[
            ToolParameter(
                name="query",
                label=I18nObject(en_US="Query"),
                human_description=I18nObject(en_US="What to search for"),
                type=ToolParameter.ToolParameterType.STRING,
                form=ToolParameter.ToolParameterForm.LLM,
                llm_description="the search query",
                required=True,
            )
        ],
        description=ToolDescription(
            human=I18nObject(en_US="Search the web"),
            llm="Search the web",
        ),
        provider_type=ToolProviderType.BUILT_IN,
        credential_id="credential-1",
    )


def _params(
    model: AgentModelConfig,
    tools: list[ToolEntity] | None = None,
    maximum_iterations: int = 5,
) -> SelfRefineParams:
    return SelfRefineParams(
        query="hello",
        instruction="answer briefly",
        model=model,
        tools=tools,
        maximum_iterations=maximum_iterations,
    )


def _tool_call_result(name: str = "search") -> LLMResult:
    return LLMResult(
        model="gpt-4o",
        message=AssistantPromptMessage(
            content="",
            tool_calls=[
                AssistantPromptMessage.ToolCall(
                    id="call-1",
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=name,
                        arguments='{"query": "meaning of life"}',
                    ),
                )
            ],
        ),
        usage=LLMUsage.empty_usage(),
    )


def _text_tool_message(text: str) -> ToolInvokeMessage:
    return ToolInvokeMessage(
        type=ToolInvokeMessage.MessageType.TEXT,
        message=ToolInvokeMessage.TextMessage(text=text),
    )


class TestSelfRefineListContent(unittest.TestCase):
    def setUp(self):
        self.strategy = SelfRefineStrategy(runtime=Mock(), session=Mock())

    def test_execute_agent_streaming_list_content(self):
        model = AgentModelConfig(
            provider="google",
            model="gemini-1.5-pro",
            mode="chat",
            entity=AIModelEntity(
                model="gemini-1.5-pro",
                model_type=ModelType.LLM,
                model_properties={},
                features=[ModelFeature.STREAM_TOOL_CALL],
            ),
        )

        def chunks():
            yield LLMResultChunk(
                model="gemini-1.5-pro",
                delta=LLMResultChunkDelta(
                    index=0,
                    message=_list_content_message("hi from gemini"),
                    usage=LLMUsage.empty_usage(),
                ),
            )

        self.strategy.session.model.llm.invoke = Mock(return_value=chunks())

        gen = self.strategy._execute_agent(_params(model), None, 1)
        result = None
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            result = stop.value

        self.assertEqual(result["output"], "hi from gemini")

    def test_execute_agent_non_streaming_list_content(self):
        model = AgentModelConfig(provider="openrouter", model="gpt-4o", mode="chat")

        self.strategy.session.model.llm.invoke = Mock(
            return_value=LLMResult(
                model="gpt-4o",
                message=_list_content_message("hi from openrouter"),
                usage=LLMUsage.empty_usage(),
            )
        )

        gen = self.strategy._execute_agent(_params(model), None, 1)
        result = None
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            result = stop.value

        self.assertEqual(result["output"], "hi from openrouter")

    def test_evaluate_output_list_content(self):
        model = AgentModelConfig(provider="google", model="gemini-1.5-pro", mode="chat")

        eval_json = '{"is_satisfactory": true, "issues": "", "score": 9}'
        self.strategy.session.model.llm.invoke = Mock(
            return_value=LLMResult(
                model="gemini-1.5-pro",
                message=_list_content_message(eval_json),
                usage=LLMUsage.empty_usage(),
            )
        )

        result = self.strategy._evaluate_output(_params(model), "some output")

        self.assertTrue(result.is_satisfactory)
        self.assertEqual(result.score, 9)

    def test_invoke_end_to_end_satisfactory_on_first_attempt(self):
        model = AgentModelConfig(provider="google", model="gemini-1.5-pro", mode="chat")

        eval_json = '{"is_satisfactory": true, "issues": "", "score": 10}'
        responses = [
            LLMResult(
                model="gemini-1.5-pro",
                message=_list_content_message("the answer"),
                usage=LLMUsage.empty_usage(),
            ),
            LLMResult(
                model="gemini-1.5-pro",
                message=_list_content_message(eval_json),
                usage=LLMUsage.empty_usage(),
            ),
        ]
        self.strategy.session.model.llm.invoke = Mock(side_effect=responses)

        messages = list(
            self.strategy._invoke(
                {
                    "query": "hello",
                    "instruction": "answer briefly",
                    "model": model.model_dump(mode="json"),
                }
            )
        )

        errors = [
            m.message.data.get("error")
            for m in messages
            if getattr(m.message, "status", None) is not None
            and m.message.status.value == "error"
        ]
        self.assertEqual(errors, [])


class TestSelfRefineTools(unittest.TestCase):
    """Tools are declared `required` in self_refine.yaml, so the tool path is the
    default configuration rather than an edge case."""

    def setUp(self):
        self.strategy = SelfRefineStrategy(runtime=Mock(), session=Mock())

    def _drain(self, gen):
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            return stop.value

    def test_execute_agent_passes_prompt_message_tools_to_llm(self):
        model = AgentModelConfig(provider="openai", model="gpt-4o", mode="chat")
        self.strategy.session.model.llm.invoke = Mock(
            return_value=LLMResult(
                model="gpt-4o",
                message=_list_content_message("done"),
                usage=LLMUsage.empty_usage(),
            )
        )

        result = self._drain(
            self.strategy._execute_agent(_params(model, [_tool_entity()]), None, 1)
        )

        self.assertEqual(result["output"], "done")
        tools = self.strategy.session.model.llm.invoke.call_args.kwargs["tools"]
        self.assertEqual(len(tools), 1)
        self.assertIsInstance(tools[0], PromptMessageTool)
        self.assertEqual(tools[0].name, "search")
        self.assertEqual(tools[0].description, "Search the web")
        self.assertEqual(tools[0].parameters["required"], ["query"])

    def test_execute_tools_invokes_with_provider_type_and_credential(self):
        tool = _tool_entity()
        self.strategy.session.tool.invoke = Mock(
            return_value=iter(
                [
                    ToolInvokeMessage(
                        type=ToolInvokeMessage.MessageType.TEXT,
                        message=ToolInvokeMessage.TextMessage(text="42"),
                    ),
                    ToolInvokeMessage(
                        type=ToolInvokeMessage.MessageType.JSON,
                        message=ToolInvokeMessage.JsonMessage(
                            json_object={"answer": 42}
                        ),
                    ),
                ]
            )
        )

        results = self._drain(
            self.strategy._execute_tools(
                tool_calls=[("call-1", "search", {"query": "meaning of life"})],
                tools=[tool],
            )
        )

        self.strategy.session.tool.invoke.assert_called_once_with(
            provider_type=ToolProviderType.BUILT_IN,
            provider="tavily",
            tool_name="search",
            parameters={"query": "meaning of life"},
            credential_id="credential-1",
        )
        self.assertEqual(results, ['42{"answer": 42}'])

    def test_execute_agent_feeds_tool_results_back_to_the_model(self):
        model = AgentModelConfig(provider="openai", model="gpt-4o", mode="chat")
        self.strategy.session.model.llm.invoke = Mock(
            side_effect=[
                _tool_call_result(),
                LLMResult(
                    model="gpt-4o",
                    message=_list_content_message("the answer is 42"),
                    usage=LLMUsage.empty_usage(),
                ),
            ]
        )
        self.strategy.session.tool.invoke = Mock(
            return_value=iter([_text_tool_message("42")])
        )

        result = self._drain(
            self.strategy._execute_agent(_params(model, [_tool_entity()]), None, 1)
        )

        # The model must see the observation, otherwise the tool call is pointless.
        self.assertEqual(self.strategy.session.model.llm.invoke.call_count, 2)
        second_round = self.strategy.session.model.llm.invoke.call_args.kwargs[
            "prompt_messages"
        ]
        tool_messages = [m for m in second_round if isinstance(m, ToolPromptMessage)]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "call-1")
        self.assertIn("42", tool_messages[0].content)
        self.assertEqual(result["output"], "the answer is 42")

    def test_maximum_iterations_caps_the_tool_loop(self):
        model = AgentModelConfig(provider="openai", model="gpt-4o", mode="chat")
        # A model that never stops asking for tools must not spin forever.
        self.strategy.session.model.llm.invoke = Mock(
            side_effect=lambda **_: _tool_call_result()
        )
        self.strategy.session.tool.invoke = Mock(
            side_effect=lambda **_: iter([_text_tool_message("42")])
        )

        self._drain(
            self.strategy._execute_agent(
                _params(model, [_tool_entity()], maximum_iterations=2), None, 1
            )
        )

        self.assertEqual(self.strategy.session.model.llm.invoke.call_count, 2)
        # The final round has no follow-up round to read the observations,
        # so its tool calls are not executed.
        self.assertEqual(self.strategy.session.tool.invoke.call_count, 1)

    def test_single_iteration_surfaces_the_tool_observation(self):
        model = AgentModelConfig(provider="openai", model="gpt-4o", mode="chat")
        self.strategy.session.model.llm.invoke = Mock(
            side_effect=lambda **_: _tool_call_result()
        )
        self.strategy.session.tool.invoke = Mock(
            return_value=iter([_text_tool_message("42")])
        )

        result = self._drain(
            self.strategy._execute_agent(
                _params(model, [_tool_entity()], maximum_iterations=1), None, 1
            )
        )

        self.assertEqual(self.strategy.session.model.llm.invoke.call_count, 1)
        self.assertEqual(result["output"], "42")


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("fail_after_call", [False, True])
def test_refinement_tool_round_and_saved_history_preserve_model_state(
    stream, fail_after_call, monkeypatch
):
    model = AgentModelConfig(
        provider="anthropic",
        model="claude",
        mode="chat",
        entity=AIModelEntity(
            model="claude",
            model_type=ModelType.LLM,
            model_properties={},
            features=[ModelFeature.STREAM_TOOL_CALL] if stream else [],
        ),
    )
    reply = _tool_call_result()
    reply.message.content = [
        TextPromptMessageContent(data="checking", opaque_body={"signature": "signed"}),
        TextPromptMessageContent(data="", opaque_body=0),
    ]
    reply.message.opaque_body = False
    first_call = reply.message.tool_calls[0]
    first_call.function.arguments = (
        '{ "query": "\\u4e2d", "id": 9007199254740993, "scale": 1e-9 }'
    )
    reply.message.tool_calls.append(
        first_call.model_copy(update={"id": "call-2"}, deep=True)
    )
    reply.usage = reply.usage.model_copy(
        update={
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "total_price": Decimal("0.02"),
        }
    )
    final = LLMResult(
        model=model.model,
        message=AssistantPromptMessage(
            content="done", opaque_body={"id": 9007199254740993}
        ),
        usage=LLMUsage.empty_usage().model_copy(
            update={
                "prompt_tokens": 30,
                "completion_tokens": 5,
                "total_tokens": 35,
                "total_price": Decimal("0.03"),
            }
        ),
    )
    requests = []
    tool_requests = []

    def respond(request):
        invocation = json.loads(request.content)["data"]["data"]
        if invocation["type"] == "tool":
            tool_requests.append(invocation["request"])
            messages = [_text_tool_message("42").model_dump(mode="json")]
        else:
            requests.append(
                [
                    ensure_prompt_message(value)
                    for value in invocation["request"]["prompt_messages"]
                ]
            )
            result = reply if len(requests) == 1 else final
            chunks = [
                LLMResultChunk(
                    model=model.model,
                    delta=LLMResultChunkDelta(
                        index=0, message=result.message, usage=result.usage
                    ),
                )
            ]
            if stream and len(requests) == 1:
                chunks = [
                    LLMResultChunk(
                        model=model.model,
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=reply.message.model_copy(
                                update={
                                    "content": reply.message.content[index : index + 1],
                                    "tool_calls": reply.message.tool_calls[
                                        index : index + 1
                                    ],
                                    "opaque_body": False if index else None,
                                }
                            ),
                            usage=reply.usage
                            if index
                            else reply.usage.model_copy(
                                update={
                                    "completion_tokens": 1,
                                    "total_tokens": 21,
                                    "total_price": Decimal("0.01"),
                                }
                            ),
                        ),
                    )
                    for index in range(2)
                ]
                chunks.append(
                    LLMResultChunk(
                        model=model.model,
                        delta=LLMResultChunkDelta(
                            index=2, message=AssistantPromptMessage(content="")
                        ),
                    )
                )
            messages = [chunk.model_dump(mode="json") for chunk in chunks]
        events = [
            {
                "session_id": "refine",
                "event": "backwards_response",
                "data": {
                    "backwards_request_id": invocation["backwards_request_id"],
                    "event": "response",
                    "message": "",
                    "data": message,
                },
            }
            for message in messages
        ]
        if fail_after_call and invocation["type"] == "llm":
            events = events[:1] + [
                {
                    "session_id": "refine",
                    "event": "backwards_response",
                    "data": {
                        "backwards_request_id": invocation["backwards_request_id"],
                        "event": "error",
                        "message": "provider stream failed",
                        "data": None,
                    },
                }
            ]
        return httpx.Response(200, text="\n".join(map(json.dumps, events)))

    client_type = httpx.Client
    monkeypatch.setattr(
        "dify_plugin.core.runtime.httpx",
        SimpleNamespace(
            Client=lambda: client_type(transport=httpx.MockTransport(respond))
        ),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        session = Session(
            session_id="refine",
            executor=executor,
            reader=StdioRequestReader(),
            writer=StdioResponseWriter(),
            dify_plugin_daemon_url="http://daemon.test",
        )
        strategy = SelfRefineStrategy(runtime=Mock(), session=session)
        output = list(
            strategy._invoke(
                {
                    "query": "hello",
                    "instruction": "answer",
                    "model": model,
                    "tools": [_tool_entity()],
                    "maximum_iterations": 2,
                    "max_refinements": 0,
                }
            )
        )
    if fail_after_call:
        assert tool_requests == []
        assert any(
            item.type == ToolInvokeMessage.MessageType.TEXT
            and "provider stream failed" in item.message.text
            for item in output
        )
        return

    assert len(tool_requests) == 2
    assert all(
        request["tool_parameters"]
        == {"query": "中", "id": 9007199254740993, "scale": 1e-9}
        for request in tool_requests
    )
    assert requests[1][-3] == reply.message
    assert requests[1][-2:] == [
        ToolPromptMessage(content="42", tool_call_id=call_id, name="search")
        for call_id in ("call-1", "call-2")
    ]
    metadata = output[-1].message.json_object
    assert metadata["total_tokens"] == 60
    assert metadata["total_price"] == pytest.approx(0.05)
    saved = metadata["model_history"]
    restored = AgentModelConfig.model_validate(
        {**model.model_dump(mode="json"), "history_prompt_messages": saved["messages"]}
    )
    assert restored.history_prompt_messages[1:] == [
        reply.message,
        *requests[1][-2:],
        final.message,
    ]
