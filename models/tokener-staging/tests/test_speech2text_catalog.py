import json
from pathlib import Path

import yaml
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey, ModelType

from scripts.sync_catalog import render_catalog


def catalog():
    return json.loads(Path("tests/fixtures/speech2text_catalog.json").read_text())


def test_speech2text_catalog_generates_registered_schemas_from_audio_metadata():
    payload = catalog()
    payload["models"][0]["audio"] = {
        "maxUploadBytes": 1500000,
        "supportedExtensions": ["wav", "webm"],
    }
    files = render_catalog(payload, model_type="speech2text")
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
