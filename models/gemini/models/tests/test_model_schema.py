from pathlib import Path

import yaml
from dify_plugin.entities.model import AIModelEntity
from models.llm.llm import GoogleLargeLanguageModel
from models.llm.model_schema import (
    INLINE_FILE_PARAMETER_NAME,
    model_accepts_file_inputs,
)


LLM_SCHEMA_DIR = Path(__file__).parents[1] / "llm"


def _load_llm_model_schemas() -> list[AIModelEntity]:
    schemas = []
    for path in LLM_SCHEMA_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            schemas.append(AIModelEntity(**data))
    return schemas


def test_inline_file_parameter_is_runtime_schema_not_yaml_duplication():
    for path in LLM_SCHEMA_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        rules = data.get("parameter_rules") or []
        assert INLINE_FILE_PARAMETER_NAME not in {rule.get("name") for rule in rules}


def test_inline_file_parameter_is_injected_for_all_file_input_models():
    llm = GoogleLargeLanguageModel(_load_llm_model_schemas())

    for schema in llm.predefined_models():
        rule_names = {rule.name for rule in schema.parameter_rules}
        has_inline_file = INLINE_FILE_PARAMETER_NAME in rule_names
        assert has_inline_file == model_accepts_file_inputs(schema), schema.model


def test_inline_file_parameter_covers_newer_gemini_models_without_yaml_edits():
    llm = GoogleLargeLanguageModel(_load_llm_model_schemas())

    pro_31 = llm.get_model_schema("gemini-3.1-pro-preview")
    assert pro_31 is not None
    assert INLINE_FILE_PARAMETER_NAME in {rule.name for rule in pro_31.parameter_rules}

    text_only = llm.get_model_schema("gemini-pro")
    assert text_only is not None
    assert INLINE_FILE_PARAMETER_NAME not in {
        rule.name for rule in text_only.parameter_rules
    }
