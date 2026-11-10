import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

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
    return AssistantPromptMessage(
        content=[TextPromptMessageContent(data=text)]
    )


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

        eval_json = '{"is_satisfactory": true, "issues": "", "score": 90}'
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
            return_value=iter([
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text="42"),
                ),
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.JSON,
                    message=ToolInvokeMessage.JsonMessage(json_object={"answer": 42}),
                ),
            ])
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


class TestSelfRefineQualityContract(unittest.TestCase):
    """The loop follows the documented score threshold and returns the best output (#3874)."""

    def setUp(self):
        self.strategy = SelfRefineStrategy(runtime=Mock(), session=Mock())
        self.model = AgentModelConfig(provider="google", model="gemini-1.5-pro", mode="chat")

    def _result(self, text: str) -> LLMResult:
        return LLMResult(
            model="gemini-1.5-pro",
            message=_list_content_message(text),
            usage=LLMUsage.empty_usage(),
        )

    def _eval(self, score: int, satisfactory: bool = False) -> LLMResult:
        return self._result(
            json.dumps({"is_satisfactory": satisfactory, "issues": "improve it", "score": score})
        )

    def _run(self, responses, max_refinements: int = 2):
        invoke = Mock(side_effect=responses)
        self.strategy.session.model.llm.invoke = invoke
        messages = list(
            self.strategy._invoke(
                {
                    "query": "hello",
                    "instruction": "answer briefly",
                    "model": self.model.model_dump(mode="json"),
                    "max_refinements": max_refinements,
                }
            )
        )
        texts = [
            m.message.text
            for m in messages
            if m.type == ToolInvokeMessage.MessageType.TEXT
        ]
        return texts[-1], invoke.call_count

    def test_satisfactory_flag_below_threshold_keeps_refining(self):
        output, calls = self._run(
            [
                self._result("draft"),
                self._eval(60, satisfactory=True),
                self._result("better"),
                self._eval(85),
            ],
            max_refinements=1,
        )
        self.assertEqual(output, "better")
        self.assertEqual(calls, 4)

    def test_stops_as_soon_as_score_reaches_threshold(self):
        output, calls = self._run(
            [self._result("good"), self._eval(80)],
            max_refinements=2,
        )
        self.assertEqual(output, "good")
        self.assertEqual(calls, 2)

    def test_returns_best_output_when_budget_is_exhausted(self):
        output, calls = self._run(
            [
                self._result("first"),
                self._eval(40),
                self._result("second"),
                self._eval(70),
                self._result("third"),
                self._eval(55),
            ],
            max_refinements=2,
        )
        # The final attempt is evaluated too, and the higher-scoring second
        # output wins over the latest one.
        self.assertEqual(calls, 6)
        self.assertEqual(output, "second")
