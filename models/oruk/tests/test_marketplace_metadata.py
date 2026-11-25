"""Metadata and marketplace consistency tests for the Oruk speech-to-text plugin."""

import re
import tomllib
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PLUGIN_ROOT / "models" / "speech2text"
ASSETS_DIR = PLUGIN_ROOT / "_assets"
PREDEFINED_MODELS = ("oruk-fourier-2b.yaml",)


def _read(relative_path: str) -> str:
    return (PLUGIN_ROOT / relative_path).read_text(encoding="utf-8")


def test_manifest_and_package_versions_stay_in_sync():
    manifest = yaml.safe_load(_read("manifest.yaml"))
    pyproject = tomllib.loads(_read("pyproject.toml"))
    uv_lock = tomllib.loads(_read("uv.lock"))
    locked_project = next(pkg for pkg in uv_lock["package"] if pkg["name"] == "oruk")

    assert manifest["author"] == "langgenius"
    assert manifest["name"] == "oruk"
    assert manifest["type"] == "plugin"
    assert manifest["resource"]["permission"]["model"]["speech2text"] is True
    assert manifest["resource"]["permission"]["model"]["llm"] is False

    versions = {
        str(manifest["version"]),
        str(pyproject["project"]["version"]),
        str(locked_project["version"]),
    }
    assert len(versions) == 1


def test_icons_and_privacy_files_exist_and_are_non_template():
    manifest = yaml.safe_load(_read("manifest.yaml"))
    provider = yaml.safe_load(_read("provider/oruk.yaml"))

    assert (PLUGIN_ROOT / manifest["privacy"]).is_file()

    declared_icons = {
        manifest["icon"],
        manifest["icon_dark"],
        provider["icon_small"]["en_US"],
        provider["icon_small_dark"]["en_US"],
        provider["icon_large"]["en_US"],
        provider["icon_large_dark"]["en_US"],
    }
    for icon_name in declared_icons:
        icon_path = ASSETS_DIR / icon_name
        assert icon_path.is_file(), f"Missing declared icon {icon_name}"
        content = icon_path.read_text(encoding="utf-8")
        assert "<svg" in content
        assert "DIFY_MARKETPLACE_TEMPLATE_ICON_DO_NOT_USE" not in content


def test_predefined_upload_limits_match_customizable_models():
    for filename in PREDEFINED_MODELS:
        text = (MODEL_DIR / filename).read_text(encoding="utf-8")
        assert re.search(r"^\s*file_upload_limit:\s*30\s*$", text, re.MULTILINE)
        assert re.search(
            r"^\s*supported_file_extensions:\s*flac,mp3,m4a,ogg,wav,webm\s*$",
            text,
            re.MULTILINE,
        )

    model_source = _read("models/speech2text/speech2text.py")
    assert "ModelPropertyKey.FILE_UPLOAD_LIMIT: 30" in model_source
    assert "MAX_AUDIO_BYTES = 30 * 1024 * 1024" in model_source


def test_readme_documents_hosted_and_self_hosted_setup():
    readme = _read("README.md")

    assert "https://speech-api.oruk.ai/v1" in readme
    assert "oruk-fourier-2b" in readme
    assert "$0.0080 / audio minute" in readme
    assert "hf download oruk/oruk-fourier-2b" in readme
    assert "CC-BY-NC-4.0" in readme
    assert "English" in readme
