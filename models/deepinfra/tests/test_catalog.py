"""Offline checks over the shipped model catalog. These run in CI without credentials."""

from pathlib import Path

import yaml
from dify_plugin.entities.model import AIModelEntity

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.deepinfra.com/v1/openai"


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
            assert schema["pricing"]["currency"] == "USD", model
            assert schema["pricing"]["unit"] == "0.000001", model


def test_llm_features_are_known() -> None:
    allowed = {"agent-thought", "tool-call", "multi-tool-call", "stream-tool-call", "vision", "document"}
    _, schemas = _catalog("llm")
    for model, schema in schemas.items():
        assert schema["model_properties"]["mode"] == "chat", model
        unknown = set(schema.get("features", [])) - allowed
        assert not unknown, f"{model}: unknown features {unknown}"


def test_max_tokens_within_context() -> None:
    _, schemas = _catalog("llm")
    for model, schema in schemas.items():
        rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
        context = schema["model_properties"]["context_size"]
        assert rules["max_tokens"]["max"] <= context, model
        assert rules["max_tokens"]["default"] <= rules["max_tokens"]["max"], model


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
