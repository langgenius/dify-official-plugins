"""Offline checks over the shipped model catalog. These run in CI without credentials."""

from pathlib import Path

import yaml
from dify_plugin.entities.model import AIModelEntity

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.deepinfra.com/v1/openai"

# Chat models DeepInfra rejects with "Tool calling is not supported for model: X".
# Probed against the live API; kept here so a regenerated catalog cannot quietly
# start advertising tool calling for them.
NO_TOOL_CALL = {
    "Gryphe/MythoMax-L2-13b",
    "NousResearch/Hermes-3-Llama-3.1-405B",
    "NousResearch/Hermes-3-Llama-3.1-70B",
    "Sao10K/L3-8B-Lunaris-v1-Turbo",
    "Sao10K/L3.1-70B-Euryale-v2.2",
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
    "meta-llama/Llama-Guard-4-12B",
    "microsoft/phi-4",
    "mistralai/Mistral-Small-24B-Instruct-2501",
    "nvidia/Nemotron-Content-Safety-3.5",
}


def _catalog(kind: str) -> tuple[list[str], dict[str, dict]]:
    directory = ROOT / "models" / kind
    position = yaml.safe_load((directory / "_position.yaml").read_text(encoding="utf-8"))
    schemas = {}
    for path in directory.glob("*.yaml"):
        if path.name == "_position.yaml":
            continue
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
        schemas[schema["model"]] = schema
    return position, schemas


def test_position_matches_files() -> None:
    for kind in ("llm", "text_embedding"):
        position, schemas = _catalog(kind)
        assert len(position) == len(set(position)), f"{kind}: duplicate entries in _position.yaml"
        assert set(position) == set(schemas), f"{kind}: _position.yaml and model files disagree"


def test_schemas_are_valid() -> None:
    for kind in ("llm", "text_embedding"):
        _, schemas = _catalog(kind)
        assert schemas, f"{kind}: no models defined"
        for model, schema in schemas.items():
            AIModelEntity.model_validate(schema)
            assert schema["model_properties"]["context_size"] > 0, model
            pricing = schema.get("pricing")
            if pricing:
                assert pricing["currency"] == "USD", model
                assert pricing["unit"] == "0.000001", model


def test_llm_features_are_known() -> None:
    allowed = {"agent-thought", "tool-call", "multi-tool-call", "stream-tool-call", "vision", "document"}
    _, schemas = _catalog("llm")
    for model, schema in schemas.items():
        assert schema["model_properties"]["mode"] == "chat", model
        unknown = set(schema.get("features", [])) - allowed
        assert not unknown, f"{model}: unknown features {unknown}"


def test_models_without_tool_support_do_not_advertise_it() -> None:
    """The whole point of probing: never claim a capability the API rejects."""
    _, schemas = _catalog("llm")
    # Assert presence rather than skipping: a renamed or dropped model must fail loudly, or the
    # guard quietly stops covering anything.
    missing = NO_TOOL_CALL - set(schemas)
    assert not missing, f"probed models are no longer in the catalog: {sorted(missing)}"
    for model in NO_TOOL_CALL:
        features = set(schemas[model].get("features", []))
        assert "tool-call" not in features, f"{model} advertises tool-call but DeepInfra rejects it"
        assert "stream-tool-call" not in features, model


def test_tool_call_features_are_paired() -> None:
    _, schemas = _catalog("llm")
    for model, schema in schemas.items():
        features = set(schema.get("features", []))
        assert ("tool-call" in features) == ("stream-tool-call" in features), model


def test_max_tokens_within_context() -> None:
    _, schemas = _catalog("llm")
    for model, schema in schemas.items():
        rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
        context = schema["model_properties"]["context_size"]
        assert rules["max_tokens"]["max"] <= context, model
        assert rules["max_tokens"]["default"] <= rules["max_tokens"]["max"], model


def test_catalog_is_substantial() -> None:
    """Guards against a regeneration that silently drops most of the catalog."""
    _, llm = _catalog("llm")
    _, emb = _catalog("text_embedding")
    assert len(llm) >= 100, f"only {len(llm)} llm models"
    assert len(emb) >= 20, f"only {len(emb)} embedding models"


def test_endpoint_is_deepinfra() -> None:
    common = (ROOT / "models" / "common.py").read_text(encoding="utf-8")
    provider = (ROOT / "provider" / "deepinfra.py").read_text(encoding="utf-8")
    assert ENDPOINT in common
    assert ENDPOINT in provider


def test_manifest_matches_provider() -> None:
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    provider = yaml.safe_load((ROOT / "provider" / "deepinfra.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == provider["provider"] == "deepinfra"
    assert manifest["author"] == "langgenius"
    permission = manifest["resource"]["permission"]["model"]
    assert permission["llm"] and permission["text_embedding"]
    for source in provider["extra"]["python"]["model_sources"]:
        assert (ROOT / source).exists(), source
    assert (ROOT / provider["extra"]["python"]["provider_source"]).exists()
    for icon in (provider["icon_small"]["en_US"], provider["icon_large"]["en_US"]):
        assert (ROOT / "_assets" / icon).exists(), icon
