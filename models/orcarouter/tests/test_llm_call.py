"""L3 live integration test: invoke every predefined model with a tiny prompt.

For each model in _position.yaml, run `Say hello in one word.` through PluginRunner
and assert at least one chunk is streamed back. Requires ORCAROUTER_API_KEY env var.

Adapted from openrouter's test_llm_call.py: env name and provider changed,
retry-on-failure kept (some upstream providers occasionally rate-limit fresh keys).
"""
from __future__ import annotations

import os
import time
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


def get_all_models() -> list[str]:
    models_dir = Path(__file__).parent.parent / "models" / "llm"
    position_file = models_dir / "_position.yaml"
    if not position_file.exists():
        raise FileNotFoundError(f"Missing model position file: {position_file}")

    data = yaml.safe_load(position_file.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"Expected a YAML list in {position_file}")

    return [item.strip() for item in data if isinstance(item, str) and item.strip()]


@pytest.mark.skipif(
    not os.getenv("ORCAROUTER_API_KEY"),
    reason="ORCAROUTER_API_KEY required for live LLM invocation test",
)
@pytest.mark.parametrize("model_name", get_all_models())
def test_llm_invoke(model_name: str) -> None:
    api_key = os.getenv("ORCAROUTER_API_KEY")

    plugin_path = os.getenv("PLUGIN_FILE_PATH")
    if not plugin_path:
        plugin_path = str(Path(__file__).parent.parent)

    payload = ModelInvokeLLMRequest(
        user_id="test_user",
        provider="orcarouter",
        model_type=ModelType.LLM,
        model=model_name,
        credentials={"api_key": api_key},
        prompt_messages=[{"role": "user", "content": "Say hello in one word."}],
        stop=None,
        tools=None,
        stream=True,
        model_parameters={},
    )

    with PluginRunner(
        config=IntegrationConfig(), plugin_package_path=plugin_path
    ) as runner:
        failure_count = 0
        while failure_count < 3:
            try:
                results: list[LLMResultChunk] = []
                for result in runner.invoke(
                    access_type=PluginInvokeType.Model,
                    access_action=ModelActions.InvokeLLM,
                    payload=payload,
                    response_type=LLMResultChunk,
                ):
                    results.append(result)
                assert len(results) > 0, f"No results received for model {model_name}"
                break
            except Exception as e:
                failure_count += 1
                time.sleep(1)
                if failure_count >= 3:
                    raise e
