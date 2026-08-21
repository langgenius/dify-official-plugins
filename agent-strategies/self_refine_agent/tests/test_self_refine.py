import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.entities.model import AIModelEntity, ModelFeature, ModelType
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    TextPromptMessageContent,
)
from dify_plugin.interfaces.agent import AgentModelConfig

from strategies.self_refine import SelfRefineParams, SelfRefineStrategy


def _list_content_message(text: str) -> AssistantPromptMessage:
    return AssistantPromptMessage(
        content=[TextPromptMessageContent(data=text)]
    )


def _params(model: AgentModelConfig) -> SelfRefineParams:
    return SelfRefineParams(
        query="hello",
        instruction="answer briefly",
        model=model,
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


if __name__ == "__main__":
    unittest.main()
