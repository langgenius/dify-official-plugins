import os
from pathlib import Path

import pytest
import yaml

from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeLLMRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.integration.run import PluginRunner


def get_all_models() -> list[str]:
    models_dir = Path(__file__).parent.parent / "models" / "llm"
    position_file = models_dir / "_position.yaml"
    data = yaml.safe_load(position_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {position_file}")
    return [str(x).strip() for x in data if str(x).strip()]


@pytest.mark.parametrize("model_name", get_all_models())
def test_llm_invoke(model_name: str) -> None:
    api_key = os.getenv("VOLCENGINE_API_KEY")
    if not api_key:
        raise ValueError("VOLCENGINE_API_KEY environment variable is required")

    plugin_path = os.getenv("PLUGIN_FILE_PATH")
    if not plugin_path:
        plugin_path = str(Path(__file__).parent.parent)

    payload = ModelInvokeLLMRequest(
        user_id="test_user",
        provider="volcengine",
        model_type=ModelType.LLM,
        model=model_name,
        credentials={
            "ark_api_key": api_key,
            "api_endpoint_host": os.getenv(
                "VOLCENGINE_API_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3"
            ),
        },
        prompt_messages=[UserPromptMessage(content="Say hello in one word.")],
        model_parameters={"max_tokens": 32},
        stop=None,
        tools=None,
        stream=True,
    )

    old_code = PluginRunner.__init__.__code__
    consts = [it if it != 30 else 120 for it in old_code.co_consts]
    PluginRunner.__init__.__code__ = old_code.replace(co_consts=tuple(consts))

    with PluginRunner(config=IntegrationConfig(), plugin_package_path=plugin_path) as runner:
        results: list[LLMResultChunk] = []
        for result in runner.invoke(
            access_type=PluginInvokeType.Model,
            access_action=ModelActions.InvokeLLM,
            payload=payload,
            response_type=LLMResultChunk,
        ):
            results.append(result)

        assert len(results) > 0, f"No results received for model {model_name}"
        full_content = "".join(
            r.delta.message.content
            for r in results
            if isinstance(r.delta.message.content, str)
        )
        assert len(full_content) > 0, f"Empty content for model {model_name}"
