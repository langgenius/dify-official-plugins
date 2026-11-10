from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load(relative: str) -> dict:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def _fields() -> dict[str, list[dict]]:
    schema = _load("provider/litellm.yaml")["model_credential_schema"]
    fields: dict[str, list[dict]] = {}
    for field in schema["credential_form_schemas"]:
        fields.setdefault(field["variable"], []).append(field)
    return fields


def test_manifest_points_at_existing_files() -> None:
    manifest = _load("manifest.yaml")

    assert manifest["name"] == "litellm"
    assert manifest["author"] == "langgenius"
    assert manifest["plugins"]["models"] == ["provider/litellm.yaml"]
    assert manifest["resource"]["permission"]["model"]["llm"] is True
    assert manifest["resource"]["permission"]["model"]["text_embedding"] is True
    assert (ROOT / manifest["privacy"]).is_file()
    assert (ROOT / "_assets" / manifest["icon"]).is_file()
    assert (ROOT / "_assets" / manifest["icon_dark"]).is_file()


def test_provider_declares_customizable_llm_and_embedding_models() -> None:
    provider = _load("provider/litellm.yaml")

    assert provider["provider"] == "litellm"
    assert provider["configurate_methods"] == ["customizable-model"]
    assert provider["supported_model_types"] == ["llm", "text-embedding"]
    assert "models" not in provider
    assert not list((ROOT / "models" / "llm").glob("*.yaml"))
    for source in [provider["extra"]["python"]["provider_source"]] + provider["extra"]["python"][
        "model_sources"
    ]:
        assert (ROOT / source).is_file()


def test_provider_icons_exist() -> None:
    provider = _load("provider/litellm.yaml")

    for key in ("icon_small", "icon_small_dark", "icon_large", "icon_large_dark"):
        assert (ROOT / "_assets" / provider[key]["en_US"]).is_file()


def test_endpoint_url_defaults_to_the_local_proxy() -> None:
    (endpoint,) = _fields()["endpoint_url"]

    assert endpoint["required"] is True
    assert endpoint["default"] == "http://localhost:4000"


def test_api_key_is_optional() -> None:
    (api_key,) = _fields()["api_key"]

    assert api_key["type"] == "secret-input"
    assert api_key["required"] is False


def test_llm_form_exposes_the_fields_the_base_class_reads() -> None:
    fields = _fields()

    (mode,) = fields["mode"]
    assert mode["required"] is True
    assert mode["default"] == "chat"
    assert {option["value"] for option in mode["options"]} == {"chat", "completion"}
    for name in ("context_size", "function_calling_type", "vision_support"):
        assert any(show["value"] == "llm" for field in fields[name] for show in field["show_on"]), (
            name
        )


def test_embedding_form_exposes_context_size_and_max_chunks() -> None:
    fields = _fields()

    for name in ("context_size", "max_chunks"):
        assert any(
            show["value"] == "text-embedding" for field in fields[name] for show in field["show_on"]
        ), name
