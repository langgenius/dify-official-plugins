from dify_plugin.integration.run import (
    PluginRunner,
)

from tests.models.__mockserver.openai import OPENAI_MOCK_SERVER_PORT, OpenAIMockServer
from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeLLMRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import UserPromptMessage


def test_openai_blocking():
    with OpenAIMockServer():
        with PluginRunner(
            config=IntegrationConfig(),
            plugin_package_path="models/openai",
        ) as runner:
            for result in runner.invoke(
                access_type=PluginInvokeType.Model,
                access_action=ModelActions.InvokeLLM,
                payload=ModelInvokeLLMRequest(
                    prompt_messages=[
                        UserPromptMessage(content="Hello, world!"),
                    ],
                    user_id="",
                    provider="openai",
                    model_type=ModelType.LLM,
                    model="gpt-3.5-turbo",
                    credentials={
                        "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                        "openai_api_key": "test",
                    },
                    model_parameters={},
                    stop=[],
                    tools=[],
                    stream=False,
                ),
                response_type=LLMResultChunk,
            ):
                assert result.delta.message.content == "Hello, world!"


def test_openai_streaming():
    pass
