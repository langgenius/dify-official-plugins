import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.llm._functional import generation_options, resolve_model_name  # noqa: E402


def test_flash_alias() -> None:
    assert resolve_model_name("minimax-m3.1-flash") == "MiniMax-M3.1-Flash"


def test_flash_yaml_has_effort_and_no_sampling() -> None:
    model_file = Path(__file__).parent.parent / "models" / "llm" / "minimax-m3.1-flash.yaml"
    model_schema = yaml.safe_load(model_file.read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in model_schema["parameter_rules"]}

    assert model_schema["model"] == "minimax-m3.1-flash"
    assert "vision" in model_schema["features"]
    assert rules["effort"]["options"] == ["low", "medium", "high", "xhigh", "max"]
    assert "temperature" not in rules
    assert "thinking" not in rules


def test_flash_effort_is_passed_and_invalid_values_dropped() -> None:
    assert generation_options({"effort": "max"}, "MiniMax-M3.1-Flash").effort == "max"
    assert generation_options({"effort": "none"}, "MiniMax-M3.1-Flash").effort is None
    assert generation_options({}, "MiniMax-M3.1-Flash").effort is None
    assert generation_options({}, "MiniMax-M3.1-Flash").exclude_reasoning_tokens is True
