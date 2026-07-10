from decimal import Decimal
from pathlib import Path
import tomllib

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
LLM = MODELS / "llm"

ADDED_MODELS = {
    "chat-latest",
    "gpt-5.1-2025-11-13",
    "gpt-5.2-2025-12-11",
    "gpt-5.2-pro",
    "gpt-5.2-pro-2025-12-11",
    "gpt-5.4-pro-2026-03-05",
    "gpt-5.5-2026-04-23",
    "gpt-5.5-pro-2026-04-23",
    "gpt-audio-1.5",
    "gpt-audio-mini-2025-12-15",
    "gpt-4o-mini-transcribe-2025-12-15",
    "gpt-4o-mini-tts-2025-12-15",
    "gpt-4o-transcribe-diarize",
    "omni-moderation-latest",
}

REMOVED_MODELS = {
    "chatgpt-4o-latest",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-instruct",
    "gpt-4",
    "gpt-4-0125-preview",
    "gpt-4-1106-preview",
    "gpt-4-turbo",
    "gpt-4-turbo-2024-04-09",
    "gpt-4-turbo-preview",
    "gpt-4.1-nano",
    "gpt-4.1-nano-2025-04-14",
    "gpt-4o",
    "gpt-4o-2024-05-13",
    "gpt-4o-audio-preview",
    "gpt-4o-audio-preview-2025-06-03",
    "gpt-4o-mini-tts",
    "gpt-4o-mini-tts-2025-03-20",
    "gpt-5-2025-08-07",
    "gpt-5-chat-latest",
    "gpt-5-mini-2025-08-07",
    "gpt-5-nano-2025-08-07",
    "gpt-5-pro-2025-10-06",
    "gpt-5.1-chat-latest",
    "gpt-5.2-chat-latest",
    "gpt-5.3-chat-latest",
    "gpt-audio-mini",
    "gpt-audio-mini-2025-10-06",
    "o1",
    "o1-mini",
    "o1-mini-2024-09-12",
    "o1-preview",
    "o1-preview-2024-09-12",
    "o3-2025-04-16",
    "o3-mini",
    "o3-mini-2025-01-31",
    "o3-pro-2025-06-10",
    "o4-mini",
    "o4-mini-2025-04-16",
    "text-moderation-stable",
}


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _model_files() -> list[Path]:
    return sorted(
        path for path in MODELS.rglob("*.yaml") if not path.name.startswith("_")
    )


def test_every_model_filename_matches_its_identifier() -> None:
    for path in _model_files():
        data = _load(path)
        assert data["model"] == path.stem
        assert data["model_type"] == path.parent.name.replace("_", "-")


def test_llm_position_is_complete_and_has_no_duplicates() -> None:
    position = _load(LLM / "_position.yaml")
    files = {path.stem for path in LLM.glob("*.yaml") if path.stem != "_position"}

    assert len(position) == len(set(position))
    assert set(position) == files


def test_catalog_adds_current_models_and_removes_retired_models() -> None:
    models = {_load(path)["model"] for path in _model_files()}

    assert ADDED_MODELS <= models
    assert REMOVED_MODELS.isdisjoint(models)


def test_llm_parameters_and_prices_are_well_formed() -> None:
    for path in LLM.glob("*.yaml"):
        if path.stem == "_position":
            continue
        data = _load(path)
        parameters = data.get("parameter_rules", [])
        names = [parameter["name"] for parameter in parameters]

        assert len(names) == len(set(names))
        assert data["model_properties"]["context_size"] > 0
        assert Decimal(data["pricing"]["input"]) >= 0
        assert Decimal(data["pricing"]["output"]) >= 0
        assert Decimal(data["pricing"]["unit"]) > 0


def test_audio_model_limits_match_the_api_contract() -> None:
    full_voices = {
        "alloy",
        "ash",
        "ballad",
        "cedar",
        "coral",
        "echo",
        "fable",
        "marin",
        "nova",
        "onyx",
        "sage",
        "shimmer",
        "verse",
    }
    legacy_voices = full_voices - {"ballad", "cedar", "marin", "verse"}
    data = _load(MODELS / "tts" / "gpt-4o-mini-tts-2025-12-15.yaml")
    assert {
        voice["mode"] for voice in data["model_properties"]["voices"]
    } == full_voices
    assert data["model_properties"]["word_limit"] == 4096
    for model in ("tts-1", "tts-1-hd"):
        data = _load(MODELS / "tts" / f"{model}.yaml")
        assert {
            voice["mode"] for voice in data["model_properties"]["voices"]
        } == legacy_voices
        assert data["model_properties"]["word_limit"] == 4096

    extensions = {"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"}
    for path in (MODELS / "speech2text").glob("*.yaml"):
        configured = _load(path)["model_properties"]["supported_file_extensions"]
        assert set(configured.split(",")) == extensions


def test_version_one_is_consistent_and_documented() -> None:
    manifest = _load(ROOT / "manifest.yaml")
    provider = _load(ROOT / "provider" / "openai.yaml")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert manifest["version"] == "1.0.0"
    assert project["project"]["version"] == "1.0.0"
    assert "Version 1.0 is a major rewrite" in readme
    permissions = manifest["resource"]["permission"]["model"]
    assert permissions["enabled"] is True
    assert all(
        permissions[model_type.replace("-", "_")] is True
        for model_type in provider["supported_model_types"]
    )


def test_code_files_stay_within_the_module_size_limit() -> None:
    paths = [ROOT / "main.py"]
    paths.extend((ROOT / "models").rglob("*.py"))
    paths.extend((ROOT / "provider").rglob("*.py"))
    paths.extend((ROOT / "tests").rglob("*.py"))
    oversized = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in paths
        if len(path.read_text(encoding="utf-8").splitlines()) > 500
    }

    assert oversized == {}
