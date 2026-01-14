import os

from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeLLMRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.integration.run import PluginRunner


def test_llm_invoke() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    plugin_path = os.getenv("PLUGIN_FILE_PATH")
    if not plugin_path:
        raise ValueError("PLUGIN_FILE_PATH environment variable is required")

    payload = ModelInvokeLLMRequest(
        user_id="test_user",
        provider="anthropic",
        model_type=ModelType.LLM,
        model="claude-haiku-4-5-20251001",
        credentials={"anthropic_api_key": api_key},
        prompt_messages=[{"role": "user", "content": "Say hello in one word."}],
        model_parameters={"max_tokens": 100},
        stop=None,
        tools=None,
        stream=True,
    )

    with PluginRunner(
        config=IntegrationConfig(), plugin_package_path=plugin_path
    ) as runner:
        results: list[LLMResultChunk] = []
        for result in runner.invoke(
            access_type=PluginInvokeType.Model,
            access_action=ModelActions.InvokeLLM,
            payload=payload,
            response_type=LLMResultChunk,
        ):
            results.append(result)

        assert len(results) > 0
        content_chunks = [r for r in results if r.delta.message.content]
        assert len(content_chunks) > 0
