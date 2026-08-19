import os
from pathlib import Path

import pytest
import yaml

from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeRerankRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.rerank import RerankResult
from dify_plugin.integration.run import PluginRunner


def get_all_rerank_models() -> list[str]:
    position_file = Path(__file__).parent.parent / "models" / "rerank" / "_position.yaml"
    try:
        data = yaml.safe_load(position_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {position_file}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Expected a YAML list in {position_file}")
    return [item.strip() for item in data if isinstance(item, str) and item.strip()]


@pytest.mark.parametrize("model_name", get_all_rerank_models())
def test_rerank_invoke(model_name: str) -> None:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY is not set")

    plugin_path = os.getenv("PLUGIN_FILE_PATH")
    if not plugin_path:
        if os.getenv("CI"):
            raise ValueError(
                "PLUGIN_FILE_PATH environment variable is required in CI when provider API key is set"
            )
        plugin_path = str(Path(__file__).parent.parent)

    payload = ModelInvokeRerankRequest(
        user_id="test_user",
        provider="openrouter",
        model_type=ModelType.RERANK,
        model=model_name,
        credentials={"api_key": api_key},
        query="What is the capital of France?",
        docs=["Berlin is the capital of Germany.", "Paris is the capital of France."],
        score_threshold=None,
        top_n=1,
    )

    with PluginRunner(config=IntegrationConfig(), plugin_package_path=plugin_path) as runner:
        results = list(
            runner.invoke(
                access_type=PluginInvokeType.Model,
                access_action=ModelActions.InvokeRerank,
                payload=payload,
                response_type=RerankResult,
            )
        )

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, RerankResult)
    assert len(result.docs) == 1
    assert result.docs[0].index == 1
