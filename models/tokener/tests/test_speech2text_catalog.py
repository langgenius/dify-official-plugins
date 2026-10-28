import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey, ModelType

from scripts.sync_catalog import CatalogError, main, render_catalog, sync_files


def catalog():
    return json.loads(Path("tests/fixtures/speech2text_catalog.json").read_text())


def test_speech2text_catalog_generates_registered_schemas_from_audio_metadata(tmp_path):
    payload = catalog()
    payload["models"][0]["audio"] = {
        "maxUploadBytes": 1500000,
        "supportedExtensions": ["wav", "webm"],
    }
    files = render_catalog(payload, model_type="speech2text")
    assert sync_files(files, check=False, output_dir=tmp_path)
    assert sync_files(files, check=True, output_dir=tmp_path)
    assert len(files) == 6
    for raw in payload["models"]:
        schema = AIModelEntity.model_validate(yaml.safe_load(files[f"{raw['id']}.yaml"]))
        assert schema.model == raw["id"]
        assert schema.model_type == ModelType.SPEECH2TEXT
        assert schema.model_properties[ModelPropertyKey.FILE_UPLOAD_LIMIT] == (
            raw["audio"]["maxUploadBytes"] / 1000000
        )
        assert schema.model_properties[ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS] == ",".join(
            raw["audio"]["supportedExtensions"]
        )
        assert schema.pricing is None
    assert yaml.safe_load(files["_position.yaml"]) == sorted(m["id"] for m in payload["models"])


def test_speech2text_catalog_skips_unrequested_models_and_preserves_llm_output():
    from test_sync_catalog import _catalog

    llm = _catalog()
    expected = render_catalog(llm)
    llm["models"] += catalog()["models"] + [
        {**deepcopy(catalog()["models"][0]), "id": "qwen3-asr-flash"},
        {"id": "qwen3-tts-flash", "modelType": "tts"},
    ]
    assert render_catalog(llm) == expected
    assert len(render_catalog(llm, model_type="speech2text")) == 7


@pytest.mark.parametrize(
    "audio",
    [
        None,
        {},
        {"maxUploadBytes": 0, "supportedExtensions": ["wav"]},
        {"maxUploadBytes": True, "supportedExtensions": ["wav"]},
        {"maxUploadBytes": 1, "supportedExtensions": []},
        {"maxUploadBytes": 1, "supportedExtensions": ["wav"] * 33},
        {"maxUploadBytes": 1, "supportedExtensions": ["../wav"]},
        {"maxUploadBytes": 1, "supportedExtensions": ["WAV"]},
        {"maxUploadBytes": 1, "supportedExtensions": [None]},
    ],
)
def test_speech2text_catalog_rejects_invalid_upload_metadata(audio):
    payload = catalog()
    payload["models"][0]["audio"] = audio
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type="speech2text")


@pytest.mark.parametrize(
    "pricing",
    [
        None,
        {"currency": "CNY", "rates": []},
        {"currency": "USD", "rates": []},
        {"currency": "USD", "rates": [None]},
        {"currency": "USD", "rates": [{}]},
    ],
)
def test_speech2text_catalog_rejects_invalid_pricing(pricing):
    payload = catalog()
    payload["models"][0]["pricing"] = pricing
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type="speech2text")


@pytest.mark.parametrize("price", [0, "NaN", "-1", "1e2", "0.0000001"])
def test_speech2text_catalog_rejects_invalid_decimal_rate(price):
    payload = catalog()
    payload["models"][0]["pricing"]["rates"][0]["price"] = price
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type="speech2text")


DURATION_RATE = {"direction": "input", "modality": "audio", "unit": "second", "price": "0.0001"}
TOKEN_RATES = [
    {"direction": direction, "modality": modality, "unit": "million_tokens", "price": price}
    for direction, modality, price in [
        ("input", "text", "2.5"),
        ("input", "audio", "6"),
        ("output", "text", "10"),
    ]
]


@pytest.mark.parametrize(
    "rates",
    [[DURATION_RATE], [DURATION_RATE, *TOKEN_RATES]],
    ids=["duration", "duration-and-tokens"],
)
def test_speech2text_catalog_accepts_duration_with_optional_token_rates(rates):
    payload = catalog()
    payload["models"][0]["pricing"]["rates"] = rates
    files = render_catalog(payload, model_type="speech2text")
    assert "pricing" not in yaml.safe_load(files[f"{payload['models'][0]['id']}.yaml"])


@pytest.mark.parametrize(
    ("field", "value"), [("direction", "both"), ("modality", "video"), ("unit", "character")]
)
def test_speech2text_catalog_rejects_invalid_rate_field(field, value):
    payload = catalog()
    payload["models"][0]["pricing"]["rates"] = [{**DURATION_RATE, field: value}]
    with pytest.raises(CatalogError):
        render_catalog(payload, model_type="speech2text")


def test_speech2text_catalog_cli_only_writes_selected_model_type(tmp_path):
    payload = catalog()
    (tmp_path / "models" / "llm").mkdir(parents=True)
    untouched = tmp_path / "models" / "llm" / "untouched.yaml"
    untouched.write_text("unrelated LLM definition\n")
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.load_catalog", return_value=deepcopy(payload)),
        patch(
            "sys.argv",
            ["sync_catalog.py", "--input", "snapshot.json", "--model-type", "speech2text"],
        ),
    ):
        assert main() == 0
    assert untouched.read_text() == "unrelated LLM definition\n"
    for raw in payload["models"]:
        assert (tmp_path / "models" / "speech2text" / f"{raw['id']}.yaml").exists()
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch(
            "scripts.sync_catalog.load_catalog",
            return_value={
                **payload,
                "models": [
                    {"id": "unsupported", "modelType": "llm"},
                ],
            },
        ),
        patch(
            "sys.argv",
            ["sync_catalog.py", "--input", "snapshot.json", "--model-type", "speech2text"],
        ),
    ):
        assert main() == 0
    assert yaml.safe_load((tmp_path / "models/speech2text/_position.yaml").read_text()) == []
    assert len(list((tmp_path / "models" / "speech2text").glob("*.yaml"))) == 1


def test_speech2text_catalog_empty_llm_selection_removes_old_definitions(tmp_path):
    llm_dir = tmp_path / "models" / "llm"
    llm_dir.mkdir(parents=True)
    for path in Path("models/llm").glob("*.yaml"):
        (llm_dir / path.name).write_bytes(path.read_bytes())
    before = {path.name: path.read_bytes() for path in llm_dir.glob("*.yaml")}
    payload = catalog()

    assert render_catalog(payload, model_type="llm") == {"_position.yaml": "[]\n"}

    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.load_catalog", return_value=payload),
        patch("sys.argv", ["sync_catalog.py", "--input", "snapshot.json", "--model-type", "llm"]),
    ):
        assert main() == 0
    assert before
    assert list(llm_dir.glob("*.yaml")) == [llm_dir / "_position.yaml"]
    assert yaml.safe_load((llm_dir / "_position.yaml").read_text()) == []
