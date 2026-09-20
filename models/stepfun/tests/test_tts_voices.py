"""Exercise the voice picker with the actual model schema, without schema mocks."""

from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from models.tts.tts import StepfunText2SpeechModel

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tts():
    schema = AIModelEntity.model_validate(
        yaml.safe_load((ROOT / "models/tts/stepaudio-3-tts.yaml").read_text())
    )
    return StepfunText2SpeechModel([schema])


@pytest.mark.parametrize(
    "language",
    [
        None,
        "",
        "en-US",
        "en",
        "en_US",
        "EN-us",
        " en-US ",
        "zh-Hans",
        "zh",
        "zh-CN",
        "zh_CN",
        "zh_Hans",
    ],
)
def test_official_voices_available_for_supported_language_aliases(tts, language):
    voices = tts.get_tts_model_voices("stepaudio-3-tts", {}, language)
    assert len(voices) == 36
    assert len({voice["value"] for voice in voices}) == 36
    assert {"name": "磁性男声", "value": "cixingnansheng"} in voices
    assert {"name": "Vibrant Youth", "value": "vibrant-youth"} in voices
    assert tts._get_model_default_voice("stepaudio-3-tts", {}) in {v["value"] for v in voices}


def test_unsupported_language_is_not_mislabeled(tts):
    assert tts.get_tts_model_voices("stepaudio-3-tts", {}, "de-DE") == []


def test_unknown_model_does_not_borrow_stepaudio_voices(tts):
    assert tts.get_tts_model_voices("unknown-model", {}, "en-US") == []
