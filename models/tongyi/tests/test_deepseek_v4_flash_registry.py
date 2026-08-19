"""
Registry/metadata tests for deepseek-v4-flash-0731 (stable release of DeepSeek-V4-Flash).

Regression tests for https://github.com/langgenius/dify-official-plugins/issues/3612:
the plugin exposed only the preview ID `deepseek-v4-flash`, so Dify rejected the
documented stable ID `deepseek-v4-flash-0731` with
"ValueError: model.name must be in the specified model list" even though the
Tongyi API serves it. Reference: https://help.aliyun.com/zh/model-studio/deepseek-v4-flash
"""

import re
from pathlib import Path

import yaml

MODELS_DIR = Path(__file__).parent.parent / "models" / "llm"
DATED_MODEL = "deepseek-v4-flash-0731"
PREVIEW_MODEL = "deepseek-v4-flash"


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_dated_model_listed_in_position():
    position = _load_yaml(MODELS_DIR / "_position.yaml")
    assert DATED_MODEL in position, f"{DATED_MODEL} missing from _position.yaml"
    # The preview ID must remain for backward compatibility.
    assert PREVIEW_MODEL in position, f"{PREVIEW_MODEL} removed from _position.yaml"


def test_dated_model_yaml_exists_with_correct_id():
    schema_path = MODELS_DIR / f"{DATED_MODEL}.yaml"
    assert schema_path.exists(), f"missing model schema file {schema_path.name}"
    schema = _load_yaml(schema_path)
    assert schema["model"] == DATED_MODEL
    assert schema["model_type"] == "llm"


def test_dated_model_inherits_flash_capabilities():
    dated = _load_yaml(MODELS_DIR / f"{DATED_MODEL}.yaml")
    preview = _load_yaml(MODELS_DIR / f"{PREVIEW_MODEL}.yaml")

    assert dated["features"] == preview["features"]
    assert set(dated["features"]) >= {
        "agent-thought",
        "tool-call",
        "multi-tool-call",
        "stream-tool-call",
    }
    assert dated["model_properties"] == preview["model_properties"]
    assert dated["parameter_rules"] == preview["parameter_rules"]
    assert dated["pricing"] == preview["pricing"]

    rule_names = {rule["name"] for rule in dated["parameter_rules"]}
    assert "enable_thinking" in rule_names
    assert "enable_search" in rule_names


def test_llm_thinking_branch_recognizes_dated_model():
    source = (MODELS_DIR / "llm.py").read_text(encoding="utf-8")
    match = re.search(
        r"thinking_deepseek_v4 = \((?P<expr>.*?)\)\n", source, flags=re.DOTALL
    )
    assert match, "thinking_deepseek_v4 branch not found in llm.py"
    expr = match.group("expr")
    assert f'"{DATED_MODEL}"' in expr, (
        f"{DATED_MODEL} not handled by the DeepSeek V4 thinking/streaming "
        "condition in llm.py"
    )
