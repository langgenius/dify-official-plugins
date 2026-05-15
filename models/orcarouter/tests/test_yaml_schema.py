"""L1 offline tests: model YAML schema correctness across llm / text_embedding / tts."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

MODELS_ROOT = Path(__file__).parent.parent / "models"
LLM_DIR = MODELS_ROOT / "llm"
EMBED_DIR = MODELS_ROOT / "text_embedding"
TTS_DIR = MODELS_ROOT / "tts"

ALLOWED_UNITS = {"0.000001", "0.001", "0.01"}


def _yaml_files(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return sorted([p for p in d.glob("*.yaml") if p.name != "_position.yaml"])


def _all_yaml_files() -> list[Path]:
    return _yaml_files(LLM_DIR) + _yaml_files(EMBED_DIR) + _yaml_files(TTS_DIR)


@pytest.mark.parametrize("yaml_path", _all_yaml_files())
def test_model_yaml_parses(yaml_path: Path) -> None:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{yaml_path.name}: top-level must be a dict"


@pytest.mark.parametrize("yaml_path", _all_yaml_files())
def test_model_yaml_has_core_fields(yaml_path: Path) -> None:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    for key in ("model", "label", "model_type", "model_properties", "pricing"):
        assert key in data, f"{yaml_path.name} missing required key: {key}"


@pytest.mark.parametrize("yaml_path", _all_yaml_files())
def test_model_yaml_pricing(yaml_path: Path) -> None:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    p = data["pricing"]
    assert p.get("currency") == "USD", f"{yaml_path.name}: currency must be USD"
    assert p.get("unit") in ALLOWED_UNITS, f"{yaml_path.name}: unknown unit {p.get('unit')!r}"
    assert float(p["input"]) >= 0, f"{yaml_path.name}: input price must be >= 0"
    if "output" in p:
        assert float(p["output"]) >= 0, f"{yaml_path.name}: output price must be >= 0"


@pytest.mark.parametrize("yaml_path", _yaml_files(LLM_DIR))
def test_llm_yaml_has_orcarouter_params(yaml_path: Path) -> None:
    """Every LLM YAML must expose orcarouter_fallback_models + orcarouter_route."""
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    names = {rule["name"] for rule in data.get("parameter_rules", [])}
    assert "orcarouter_fallback_models" in names, f"{yaml_path.name} missing fallback_models"
    assert "orcarouter_route" in names, f"{yaml_path.name} missing route"


@pytest.mark.parametrize("yaml_path", _yaml_files(TTS_DIR))
def test_tts_yaml_has_voices(yaml_path: Path) -> None:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    voices = data["model_properties"].get("voices") or []
    assert len(voices) >= 1, f"{yaml_path.name}: must declare at least one voice"
    assert data["model_properties"].get("default_voice"), f"{yaml_path.name}: missing default_voice"


def test_llm_orcarouter_auto_first() -> None:
    positions = yaml.safe_load((LLM_DIR / "_position.yaml").read_text(encoding="utf-8")) or []
    assert positions[0] == "orcarouter/auto", f"expected orcarouter/auto first, got {positions[0]!r}"


@pytest.mark.parametrize("dir_path", [LLM_DIR, EMBED_DIR, TTS_DIR])
def test_position_entries_match_files(dir_path: Path) -> None:
    pos_file = dir_path / "_position.yaml"
    if not pos_file.exists():
        pytest.skip(f"no position file in {dir_path.name}")
    positions = set(yaml.safe_load(pos_file.read_text(encoding="utf-8")) or [])
    yaml_models = set()
    for f in _yaml_files(dir_path):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        yaml_models.add(data["model"])
    missing = positions - yaml_models
    orphan = yaml_models - positions
    assert not missing, f"{dir_path.name}/_position.yaml references missing YAMLs: {missing}"
    assert not orphan, f"{dir_path.name} has orphan YAMLs not in _position.yaml: {orphan}"
