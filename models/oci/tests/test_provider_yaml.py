"""Load provider/oci.yaml through the SDK's ModelProviderConfiguration, i.e. the same code
path the plugin daemon uses, so a broken glob, yaml or model entity fails here first."""

import sys
from pathlib import Path

from dify_plugin.core.utils.yaml_loader import load_yaml_file
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.provider import ModelProviderConfiguration

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def test_provider_configuration_loads_like_the_daemon(monkeypatch):
    monkeypatch.chdir(ROOT_DIR)
    config = ModelProviderConfiguration(**load_yaml_file("provider/oci.yaml"))

    by_type: dict[ModelType, set[str]] = {}
    for entity in config.models:
        by_type.setdefault(entity.model_type, set()).add(entity.model)

    assert {"xai.grok-4.7", "cohere.command-a-vision", "meta.llama-4-scout-17b-16e-instruct"} <= by_type[ModelType.LLM]
    assert by_type[ModelType.TEXT_EMBEDDING] >= {"cohere.embed-v4.0"}
    assert by_type[ModelType.RERANK] == {"cohere.rerank-v4.0-fast"}
    assert {t.value for t in config.supported_model_types} == {"llm", "text-embedding", "rerank"}
    # NOTE: `position` is resolved by the plugin daemon, not by the Python SDK, so it is not asserted here.

    assert (ROOT_DIR / config.extra.python.provider_source).is_file()
    for source in config.extra.python.model_sources:
        assert (ROOT_DIR / source).is_file(), source
