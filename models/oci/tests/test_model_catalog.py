"""Offline integrity checks for the predefined model catalog shipped with the plugin.

Every yaml under models/*/models must load into the SDK's AIModelEntity, model ids must
be unique and listed in the matching _position.yaml, the provider yaml must wire every
model type it declares, and ids that OCI has retired on-demand must stay flagged
``deprecated: true`` (hidden from new selections but still resolvable by existing apps).
"""

import sys
from pathlib import Path

import pytest
from dify_plugin.core.utils.yaml_loader import load_yaml_file
from dify_plugin.entities.model import AIModelEntity, ModelType

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

PROVIDER = load_yaml_file(str(ROOT_DIR / "provider" / "oci.yaml"))
MANIFEST = load_yaml_file(str(ROOT_DIR / "manifest.yaml"))

# model type key in provider yaml -> ModelType
MODEL_TYPES = {
    "llm": ModelType.LLM,
    "text_embedding": ModelType.TEXT_EMBEDDING,
    "rerank": ModelType.RERANK,
}

# Retired on-demand by OCI (https://docs.oracle.com/en-us/iaas/Content/generative-ai/deprecating-on-demand.htm)
RETIRED_ON_DEMAND = {
    "xai.grok-4",
    "xai.grok-3",
    "xai.grok-3-mini",
    "xai.grok-3-fast",
    "xai.grok-3-mini-fast",
    "cohere.command-r-08-2024",
    "cohere.command-r-plus-08-2024",
    "meta.llama-3.1-405b-instruct",
    "meta.llama-3.2-90b-vision-instruct",
    "cohere.embed-english-v3.0",
    "cohere.embed-english-light-v3.0",
    "cohere.embed-multilingual-v3.0",
    "cohere.embed-multilingual-light-v3.0",
    "cohere.embed-english-light-v2.0",
}

# Current on-demand catalog entries the plugin must expose.
EXPECTED_ACTIVE = {
    ModelType.LLM: {
        "xai.grok-4.7",
        "xai.grok-4.6",
        "xai.grok-4.3",
        "xai.grok-4.20-reasoning",
        "xai.grok-4.20-non-reasoning",
        "google.gemini-2.5-pro",
        "google.gemini-2.5-flash",
        "google.gemini-2.5-flash-lite",
        "openai.gpt-oss-120b",
        "openai.gpt-oss-20b",
        "cohere.command-a-03-2025",
        "cohere.command-a-vision",
        "meta.llama-4-maverick-17b-128e-instruct-fp8",
        "meta.llama-4-scout-17b-16e-instruct",
        "meta.llama-3.3-70b-instruct",
    },
    ModelType.TEXT_EMBEDDING: {"cohere.embed-v4.0"},
    ModelType.RERANK: {"cohere.rerank-v4.0-fast"},
}


def _model_files(model_type_key: str) -> list[Path]:
    files: list[Path] = []
    for pattern in PROVIDER["models"][model_type_key]["predefined"]:
        files.extend(sorted(ROOT_DIR.glob(pattern)))
    return files


def _entities(model_type_key: str) -> dict[str, AIModelEntity]:
    entities: dict[str, AIModelEntity] = {}
    for path in _model_files(model_type_key):
        data = load_yaml_file(str(path))
        entity = AIModelEntity(**data)
        assert entity.model not in entities, f"duplicate model id {entity.model} ({path})"
        entities[entity.model] = entity
    return entities


@pytest.mark.parametrize("model_type_key", sorted(MODEL_TYPES))
def test_every_model_yaml_loads(model_type_key: str) -> None:
    entities = _entities(model_type_key)
    assert entities, f"no models found for {model_type_key}"
    for entity in entities.values():
        assert entity.model_type == MODEL_TYPES[model_type_key], entity.model
        assert "context_size" in {k.value for k in entity.model_properties}, entity.model


@pytest.mark.parametrize("model_type_key", sorted(MODEL_TYPES))
def test_position_file_matches_models(model_type_key: str) -> None:
    position = load_yaml_file(str(ROOT_DIR / PROVIDER["models"][model_type_key]["position"]))
    ids = set(_entities(model_type_key))
    assert set(position) == ids, (
        f"{model_type_key}: _position.yaml and model yamls disagree: "
        f"only in position={sorted(set(position) - ids)} only in models={sorted(ids - set(position))}"
    )
    assert len(position) == len(set(position)), "duplicate ids in _position.yaml"


@pytest.mark.parametrize("model_type_key", sorted(MODEL_TYPES))
def test_expected_active_models_present_and_not_deprecated(model_type_key: str) -> None:
    entities = _entities(model_type_key)
    missing = EXPECTED_ACTIVE[MODEL_TYPES[model_type_key]] - set(entities)
    assert not missing, f"missing current catalog ids: {sorted(missing)}"
    for model_id in EXPECTED_ACTIVE[MODEL_TYPES[model_type_key]]:
        assert not entities[model_id].deprecated, f"{model_id} must not be flagged deprecated"


def test_retired_ids_are_kept_but_flagged_deprecated() -> None:
    all_entities = {}
    for key in MODEL_TYPES:
        all_entities.update(_entities(key))
    for model_id in RETIRED_ON_DEMAND:
        assert model_id in all_entities, f"retired id {model_id} must stay resolvable"
        assert all_entities[model_id].deprecated, f"retired id {model_id} must be deprecated: true"


def test_provider_declares_every_model_type() -> None:
    assert set(PROVIDER["supported_model_types"]) == {"llm", "text-embedding", "rerank"}
    assert set(PROVIDER["models"]) == set(MODEL_TYPES)
    sources = set(PROVIDER["extra"]["python"]["model_sources"])
    assert {"models/llm/llm.py", "models/text_embedding/text_embedding.py", "models/rerank/rerank.py"} <= sources
    for source in sources:
        assert (ROOT_DIR / source).is_file(), source


def test_manifest_permissions_cover_supported_model_types() -> None:
    perms = MANIFEST["resource"]["permission"]["model"]
    assert perms["enabled"] is True
    assert perms["llm"] is True
    assert perms["text_embedding"] is True
    assert perms["rerank"] is True


def test_reasoning_models_expose_uppercase_reasoning_effort() -> None:
    entities = _entities("llm")
    for model_id in ("xai.grok-4.7", "xai.grok-4.6", "xai.grok-4.3", "openai.gpt-oss-120b", "openai.gpt-oss-20b"):
        rules = {r.name: r for r in entities[model_id].parameter_rules}
        assert "reasoningEffort" in rules, model_id
        # OCI only accepts upper-case enum values; "low"/"xhigh" are rejected with HTTP 400.
        assert rules["reasoningEffort"].options == ["LOW", "MEDIUM", "HIGH"], model_id
        assert rules["reasoningEffort"].default is None, model_id
    # OCI rejects reasoningEffort for both Grok 4.20 variants ("does not support parameter reasoningEffort").
    for model_id in ("xai.grok-4.20-reasoning", "xai.grok-4.20-non-reasoning"):
        assert "reasoningEffort" not in {r.name for r in entities[model_id].parameter_rules}, model_id


def test_command_a_vision_has_no_tool_features() -> None:
    # OCI: "tool use is not supported by the provided model" for cohere.command-a-vision.
    features = {f.value for f in _entities("llm")["cohere.command-a-vision"].features or []}
    assert "vision" in features
    assert not features & {"tool-call", "multi-tool-call", "stream-tool-call"}


def test_on_demand_output_caps() -> None:
    entities = _entities("llm")
    for model_id in ("meta.llama-4-maverick-17b-128e-instruct-fp8", "meta.llama-4-scout-17b-16e-instruct"):
        rules = {r.name: r for r in entities[model_id].parameter_rules}
        # OCI caps on-demand responses for Llama 4 at 4,000 tokens per run.
        assert rules["maxTokens"].max == 4000, model_id
    props = lambda model_id: {k.value: v for k, v in entities[model_id].model_properties.items()}  # noqa: E731
    assert props("meta.llama-4-maverick-17b-128e-instruct-fp8")["context_size"] == 512000
    assert props("meta.llama-4-scout-17b-16e-instruct")["context_size"] == 192000


def test_embed_v4_limits() -> None:
    entity = _entities("text_embedding")["cohere.embed-v4.0"]
    props = {k.value: v for k, v in entity.model_properties.items()}
    assert props["context_size"] == 128000
    # OCI rejects more than 96 inputs per embedText request.
    assert props["max_chunks"] <= 96
