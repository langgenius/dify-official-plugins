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
from dify_plugin.integration.run import PluginRunner


EXCLUDED_MODELS = {
    "qwen2.5-1.5b-instruct",
    "qwen2.5-0.5b-instruct",
}


def get_all_models() -> list[str]:
    models_dir = Path(__file__).parent.parent / "models" / "llm"
    position_file = models_dir / "_position.yaml"
    if not position_file.exists():
        raise FileNotFoundError(f"Missing model position file: {position_file}")

    try:
        data = yaml.safe_load(position_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {position_file}") from exc

    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"Expected a YAML list in {position_file}")

    models: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            model_name = item.strip()
            if model_name in EXCLUDED_MODELS:
                continue
            models.append(model_name)
    return models


@pytest.mark.parametrize("model_name", get_all_models())
def test_llm_invoke(model_name: str) -> None:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY environment variable is required")

    plugin_path = os.getenv("PLUGIN_FILE_PATH")
    if not plugin_path:
        plugin_path = str(Path(__file__).parent.parent)

    payload = ModelInvokeLLMRequest(
        user_id="test_user",
        provider="tongyi",
        model_type=ModelType.LLM,
        model=model_name,
        credentials={"dashscope_api_key": api_key},
        prompt_messages=[{"role": "user", "content": "Say hello in one word."}],
        model_parameters={"max_tokens": 100},
        stop=None,
        tools=None,
        stream=True,
    )

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
            r.delta.message.content for r in results if r.delta.message.content
        )
        assert len(full_content) > 0, f"Empty content for model {model_name}"
