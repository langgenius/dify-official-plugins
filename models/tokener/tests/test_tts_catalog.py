import json
from pathlib import Path
from unittest.mock import patch

import yaml
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey, ModelType
from test_catalog_export import source_models as source_models

from scripts.sync_catalog import main, render_catalog


def catalog():
    return json.loads(Path("tests/fixtures/tts_catalog.json").read_text())


def test_tts_catalog_exposes_character_limit_and_audio_format():
    payload = catalog()
    payload["models"][0]["audio"] = {
        "voices": [{"id": "custom", "languages": ["zh-Hans", "en-US"]}],
        "defaultVoice": "custom",
        "wordLimit": 7,
        "audioFormat": "opus",
    }
    files = render_catalog(payload, model_type="tts")
    for raw in payload["models"]:
        content = yaml.safe_load(files[f"{raw['id']}.yaml"])
        entity = AIModelEntity.model_validate(content)
        assert entity.model_type == ModelType.TTS
        assert entity.model_properties[ModelPropertyKey.WORD_LIMIT] == raw["audio"]["wordLimit"]
        assert entity.model_properties[ModelPropertyKey.AUDIO_TYPE] == raw["audio"]["audioFormat"]


def test_tts_catalog_accepts_multidimensional_rates_without_publishing_partial_price():
    payload = catalog()
    payload["models"][0]["pricing"]["rates"] = [
        {"direction": "input", "modality": "text", "unit": "character", "price": "0.000001"},
        {"direction": "input", "modality": "text", "unit": "million_tokens", "price": "1"},
        {"direction": "output", "modality": "audio", "unit": "second", "price": "2"},
    ]
    content = yaml.safe_load(render_catalog(payload, model_type="tts")["tts-1.yaml"])
    assert "pricing" not in content


def test_tts_catalog_cli_only_writes_selected_type(tmp_path, source_models):
    payload = catalog()
    for kind in ("llm", "speech2text"):
        (tmp_path / "models" / kind).mkdir(parents=True)
        (tmp_path / "models" / kind / "keep.yaml").write_bytes(b"keep bytes\n")
    args = [
        "sync_catalog.py",
        "--input",
        "snapshot.json",
        "--model-type",
        "tts",
        "--source-root",
        str(source_models),
    ]
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("scripts.sync_catalog.load_catalog", return_value=payload),
        patch("sys.argv", args),
    ):
        assert main() == 0
    for kind in ("llm", "speech2text"):
        assert (tmp_path / "models" / kind / "keep.yaml").read_bytes() == b"keep bytes\n"


def test_tts_catalog_rejects_non_dify_locale(tmp_path, source_models):
    payload = catalog()
    payload["models"][0]["audio"]["voices"][0]["languages"] = ["en-US", "zh-CN"]
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("scripts.sync_catalog.load_catalog", return_value=payload),
        patch(
            "sys.argv",
            ["sync_catalog.py", "--input", "snapshot.json", "--source-root", str(source_models)],
        ),
    ):
        assert main() == 1
