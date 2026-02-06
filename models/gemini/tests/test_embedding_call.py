import os
from pathlib import Path

import pytest
import yaml

from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeTextEmbeddingRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult
from dify_plugin.integration.run import PluginRunner


def get_all_embedding_models() -> list[str]:
    models_dir = Path(__file__).parent.parent / "models" / "text_embedding"
    position_file = models_dir / "_position.yaml"
    if not position_file.exists():
        return []

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
            models.append(item.strip())
    return models


@pytest.mark.parametrize("model_name", get_all_embedding_models())
def test_embedding_invoke(model_name: str) -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")

    plugin_path = os.getenv("PLUGIN_FILE_PATH")
    if not plugin_path:
        plugin_path = str(Path(__file__).parent.parent)

    payload = ModelInvokeTextEmbeddingRequest(
        user_id="test_user",
        provider="google",
        model_type=ModelType.TEXT_EMBEDDING,
        model=model_name,
        credentials={"google_api_key": api_key},
        texts=[
            "Hello, how are you?",
            "Dify is an LLM application development platform.",
        ],
    )

    with PluginRunner(
        config=IntegrationConfig(), plugin_package_path=plugin_path
    ) as runner:
        result = runner.invoke(
            access_type=PluginInvokeType.Model,
            access_action=ModelActions.InvokeTextEmbedding,
            payload=payload,
            response_type=TextEmbeddingResult,
        )

        assert isinstance(result, TextEmbeddingResult)
        assert len(result.embeddings) == 2
        assert len(result.embeddings[0]) > 0
        assert result.usage.total_tokens > 0
