from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models" / "llm"

EXPECTED = {
    "sarvam-105b": {
        "context": 128000,
        "vision": False,
        "reasoning": ["none", "low", "medium", "high"],
        "default_effort": "low",
        "temperature": 1.0,
        "max_tokens_default": 4096,
        "input": 0.1595744681,
        "output": 0.6382978723,
    },
    "sarvam-105b-conversations": {
        "context": 32000,
        "vision": False,
        "reasoning": None,
        "default_effort": None,
        "temperature": 0.6,
        "max_tokens_default": 2048,
        "input": 0.1595744681,
        "output": 0.6382978723,
    },
    "glm5.3": {
        "context": 1048576,
        "vision": False,
        "reasoning": ["low", "high", "max"],
        "default_effort": "max",
        "temperature": 0.7,
        "max_tokens_default": 32768,
        "input": 1.340425532,
        "output": 4.148936170,
    },
    "glm5.3-flash": {
        "context": 1048576,
        "vision": True,
        "reasoning": ["low", "high", "max"],
        "default_effort": "high",
        "temperature": 0.7,
        "max_tokens_default": 32768,
        "input": 0.1436170213,
        "output": 0.4787234043,
    },
    "gemma4": {
        "context": 262144,
        "vision": True,
        "reasoning": ["none", "low", "high", "max"],
        "default_effort": "none",
        "temperature": 0.7,
        "max_tokens_default": 8192,
        "input": 0.3723404255,
        "output": 0.9574468085,
    },
    "deepseekv4.1-flash-1017": {
        "context": 1048576,
        "vision": True,
        "reasoning": ["none", "low", "high", "max"],
        "default_effort": "high",
        "temperature": 0.7,
        "max_tokens_default": 32768,
        "input": 0.1489361702,
        "output": 0.5851063830,
    },
    "deepseekv4.1-flash-1017-interactive": {
        "context": 1048576,
        "vision": True,
        "reasoning": ["none", "low", "high", "max"],
        "default_effort": "high",
        "temperature": 0.7,
        "max_tokens_default": 32768,
        "input": 0.2659574468,
        "output": 1.117021277,
    },
}


def load_model(name: str) -> dict:
    return yaml.safe_load((MODELS_DIR / f"{name}.yaml").read_text())


def parameter(model: dict, name: str) -> dict | None:
    for rule in model["parameter_rules"]:
        if rule["name"] == name:
            return rule
    return None


def test_model_files_match_expected() -> None:
    files = sorted(
        path.stem
        for path in MODELS_DIR.glob("*.yaml")
        if path.name != "_position.yaml"
    )
    assert files == sorted(EXPECTED)


def test_model_id_matches_filename() -> None:
    for name in EXPECTED:
        assert load_model(name)["model"] == name


def test_model_type_and_mode() -> None:
    for name in EXPECTED:
        model = load_model(name)
        assert model["model_type"] == "llm"
        assert model["model_properties"]["mode"] == "chat"


def test_context_sizes() -> None:
    for name, expected in EXPECTED.items():
        model = load_model(name)
        assert model["model_properties"]["context_size"] == expected["context"]


def test_vision_feature() -> None:
    for name, expected in EXPECTED.items():
        features = load_model(name)["features"]
        assert ("vision" in features) is expected["vision"], name


def test_reasoning_options_and_default() -> None:
    for name, expected in EXPECTED.items():
        rule = parameter(load_model(name), "reasoning_effort")
        if expected["reasoning"] is None:
            assert rule is None, name
            continue
        assert rule is not None, name
        assert rule["options"] == expected["reasoning"], name
        assert rule["default"] == expected["default_effort"], name


def test_tool_and_structured_features() -> None:
    required = {"tool-call", "multi-tool-call", "stream-tool-call", "structured-output"}
    for name in EXPECTED:
        features = set(load_model(name)["features"])
        assert required <= features, name


def test_temperature_defaults() -> None:
    for name, expected in EXPECTED.items():
        rule = parameter(load_model(name), "temperature")
        assert rule is not None, name
        assert rule["default"] == expected["temperature"], name


def test_max_tokens_within_context() -> None:
    for name in EXPECTED:
        model = load_model(name)
        rule = parameter(model, "max_tokens")
        assert rule is not None, name
        assert rule["default"] <= rule["max"], name
        assert rule["max"] <= model["model_properties"]["context_size"], name


def test_pricing() -> None:
    for name, expected in EXPECTED.items():
        pricing = load_model(name)["pricing"]
        assert pricing["unit"] == "0.000001", name
        assert pricing["currency"] == "USD", name
        assert float(pricing["input"]) == pytest.approx(expected["input"]), name
        assert float(pricing["output"]) == pytest.approx(expected["output"]), name


def test_position_file() -> None:
    position = yaml.safe_load((MODELS_DIR / "_position.yaml").read_text())
    assert position == list(EXPECTED)


def test_no_duplicate_model_ids() -> None:
    ids = [load_model(name)["model"] for name in EXPECTED]
    assert len(ids) == len(set(ids))
