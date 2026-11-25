from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_provider_identity() -> None:
    provider = load_yaml(ROOT / "provider" / "sarvam.yaml")
    assert provider["provider"] == "sarvam"
    assert provider["label"]["en_US"] == "Sarvam"
    assert provider["supported_model_types"] == ["llm"]
    assert provider["configurate_methods"] == ["predefined-model"]


def test_provider_credentials() -> None:
    provider = load_yaml(ROOT / "provider" / "sarvam.yaml")
    forms = provider["provider_credential_schema"]["credential_form_schemas"]
    api_key = next(form for form in forms if form["variable"] == "api_key")
    assert api_key["type"] == "secret-input"
    assert api_key["required"] is True

    endpoint = next(form for form in forms if form["variable"] == "endpoint_url")
    assert endpoint["type"] == "text-input"
    assert endpoint["required"] is False
    assert endpoint["default"] == "https://api.sarvam.ai/v2"


def test_provider_model_paths_exist() -> None:
    provider = load_yaml(ROOT / "provider" / "sarvam.yaml")
    assert (ROOT / provider["models"]["llm"]["position"]).is_file()
    assert provider["models"]["llm"]["predefined"] == ["models/llm/*.yaml"]
    assert (ROOT / provider["extra"]["python"]["provider_source"]).is_file()
    for source in provider["extra"]["python"]["model_sources"]:
        assert (ROOT / source).is_file()


def test_manifest() -> None:
    manifest = load_yaml(ROOT / "manifest.yaml")
    assert manifest["author"] == "langgenius"
    assert manifest["name"] == "sarvam"
    assert manifest["version"] == "0.0.1"
    assert manifest["type"] == "plugin"
    assert manifest["icon"] == "icon.svg"
    assert manifest["icon_dark"] == "icon-dark.svg"
    assert manifest["network"]["domains"] == ["api.sarvam.ai"]
    assert manifest["plugins"]["models"] == ["provider/sarvam.yaml"]
    assert manifest["meta"]["runner"]["language"] == "python"
    assert manifest["meta"]["runner"]["version"] == "3.12"
    assert manifest["meta"]["runner"]["entrypoint"] == "main"
    assert manifest["resource"]["permission"]["model"]["llm"] is True


def test_manifest_icons_exist() -> None:
    manifest = load_yaml(ROOT / "manifest.yaml")
    assert (ROOT / "_assets" / manifest["icon"]).is_file()
    assert (ROOT / "_assets" / manifest["icon_dark"]).is_file()


def test_privacy_file_exists() -> None:
    manifest = load_yaml(ROOT / "manifest.yaml")
    assert manifest["privacy"] == "PRIVACY.md"
    assert (ROOT / "PRIVACY.md").is_file()
