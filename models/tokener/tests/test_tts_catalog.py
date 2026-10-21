import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey, ModelType

from scripts.sync_catalog import CatalogError, main, render_catalog, sync_files


def catalog():
    return json.loads(Path("tests/fixtures/tts_catalog.json").read_text())


def test_tts_catalog_generates_sdk_metadata_without_pricing_or_parameter_rules():
    payload = catalog()
    payload["models"][0]["audio"] = {
        "voices": [{"id": "custom", "languages": ["zh-Hans", "en-US"]}],
        "defaultVoice": "custom",
        "wordLimit": 7,
        "audioFormat": "opus",
    }
    files = render_catalog(payload, model_type="tts")
    assert set(files) == {"tts-1.yaml", "tts-1-hd.yaml", "_position.yaml"}
    for raw in payload["models"]:
        content = yaml.safe_load(files[f"{raw['id']}.yaml"])
        entity = AIModelEntity.model_validate(content)
        assert entity.model_type == ModelType.TTS
        assert (
            entity.model_properties[ModelPropertyKey.DEFAULT_VOICE] == raw["audio"]["defaultVoice"]
        )
        assert entity.model_properties[ModelPropertyKey.WORD_LIMIT] == raw["audio"]["wordLimit"]
        assert entity.model_properties[ModelPropertyKey.AUDIO_TYPE] == raw["audio"]["audioFormat"]
        assert entity.model_properties[ModelPropertyKey.VOICES] == [
            {"mode": voice["id"], "name": voice["id"], "language": voice["languages"]}
            for voice in raw["audio"]["voices"]
        ]
        assert entity.pricing is None
        assert not entity.parameter_rules
    assert yaml.safe_load(files["_position.yaml"]) == ["tts-1", "tts-1-hd"]


def test_tts_catalog_ignores_other_audio_models_and_keeps_existing_type_outputs():
    from test_speech2text_catalog import catalog as speech2text_catalog
    from test_sync_catalog import _catalog

    llm, stt, tts = _catalog(), speech2text_catalog(), catalog()
    mixed = {
        **tts,
        "models": tts["models"]
        + stt["models"]
        + llm["models"]
        + [
            {"id": "gpt-4o-mini-tts-2025-12-15", "modelType": "tts"},
            {"id": "qwen3-tts-flash", "modelType": "tts"},
        ],
    }
    assert render_catalog(mixed, model_type="tts") == render_catalog(tts, model_type="tts")
    assert render_catalog(mixed) == render_catalog(
        {**llm, "catalogRevision": tts["catalogRevision"]}
    )
    assert render_catalog(mixed, model_type="speech2text") == render_catalog(
        stt, model_type="speech2text"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("voices", []),
        ("voices", [{}]),
        ("voices", [None]),
        ("voices", [{"id": "a", "languages": []}] * 129),
        ("voices", [{"id": "", "languages": []}]),
        ("voices", [{"id": "alloy", "languages": "en-US"}]),
        ("voices", [{"id": "alloy", "languages": [None]}]),
        ("defaultVoice", "missing"),
        ("defaultVoice", ""),
        ("wordLimit", 0),
        ("wordLimit", True),
        ("wordLimit", 1.5),
        ("audioFormat", "ogg"),
    ],
)
def test_tts_catalog_rejects_invalid_audio_metadata(field, value):
    payload = catalog()
    payload["models"][0]["audio"][field] = value
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type="tts")


def test_tts_catalog_accepts_multidimensional_rates_without_publishing_partial_price():
    payload = catalog()
    payload["models"][0]["pricing"]["rates"] = [
        {"direction": "input", "modality": "text", "unit": "character", "price": "0.000001"},
        {"direction": "input", "modality": "text", "unit": "million_tokens", "price": "1"},
        {"direction": "output", "modality": "audio", "unit": "second", "price": "2"},
    ]
    content = yaml.safe_load(render_catalog(payload, model_type="tts")["tts-1.yaml"])
    assert "pricing" not in content


@pytest.mark.parametrize(
    "pricing",
    [
        None,
        {"currency": "CNY", "rates": []},
        {"currency": "USD", "rates": []},
        {"currency": "USD", "rates": [None]},
        {
            "currency": "USD",
            "rates": [
                {
                    "direction": "input",
                    "modality": "text",
                    "unit": "character",
                    "price": "0.0000001",
                }
            ],
        },
    ],
)
def test_tts_catalog_rejects_invalid_pricing(pricing):
    payload = catalog()
    payload["models"][0]["pricing"] = pricing
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type="tts")


def test_tts_catalog_cli_only_writes_tts_and_rejects_empty_selection_without_writes(tmp_path):
    payload = catalog()
    for kind in ("llm", "speech2text"):
        (tmp_path / "models" / kind).mkdir(parents=True)
        (tmp_path / "models" / kind / "keep.yaml").write_bytes(b"keep bytes\n")
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.fetch_catalog", return_value=payload),
        patch("sys.argv", ["sync_catalog.py", "--model-type", "tts"]),
    ):
        assert main() == 0
    assert sync_files(
        render_catalog(payload, model_type="tts"), check=True, output_dir=tmp_path / "models/tts"
    )
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.yaml")}
    for model_type, rows in [
        ("llm", payload["models"]),
        ("speech2text", payload["models"]),
        ("tts", [{"id": "gpt-4o-mini-tts-2025-12-15", "modelType": "tts"}]),
    ]:
        with (
            patch("scripts.sync_catalog.ROOT", tmp_path),
            patch(
                "scripts.sync_catalog.fetch_catalog",
                return_value={**deepcopy(payload), "models": rows},
            ),
            patch("sys.argv", ["sync_catalog.py", "--model-type", model_type]),
        ):
            assert main() == 1
        assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.yaml")} == before


@pytest.mark.parametrize("model_type", ["tts", "speech2text"])
def test_tts_shared_audio_pricing_rejects_non_string_units(model_type):
    from test_speech2text_catalog import catalog as speech2text_catalog

    payload = catalog() if model_type == "tts" else speech2text_catalog()
    payload["models"][0]["pricing"]["rates"][0]["unit"] = []
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type=model_type)


@pytest.mark.parametrize("audio_format", ["wav", "flac"])
def test_tts_catalog_rejects_unsafe_audio_format_without_writing_files(tmp_path, audio_format):
    payload = catalog()
    payload["models"][0]["audio"]["audioFormat"] = audio_format
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type="tts")
    target = tmp_path / "models/tts"
    target.mkdir(parents=True)
    (target / "keep.yaml").write_bytes(b"existing model bytes\n")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.fetch_catalog", return_value=payload),
        patch("sys.argv", ["sync_catalog.py", "--model-type", "tts"]),
    ):
        assert main() == 1
    assert {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    } == before
