from pathlib import Path

import yaml


def test_qwen38_max_schema_matches_aihubmix_facts() -> None:
    schema_path = Path(__file__).parents[1] / "models" / "llm" / "qwen3.8-max.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}

    assert schema["model_properties"]["context_size"] == 991_000
    assert rules["max_completion_tokens"]["max"] == 128_000
    assert schema["pricing"] == {
        "input": "1.69",
        "output": "5.07",
        "unit": "0.000001",
        "currency": "USD",
    }
