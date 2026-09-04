from pathlib import Path

import yaml

from models.llm.anthropic import AnthropicLargeLanguageModel, PromptCachingHandler
from models.llm.google import NO_SAMPLING_OR_PREFILL_MODELS


MODEL_DIR = Path(__file__).parents[1] / "models" / "llm"


def _schema(model: str) -> dict:
    return yaml.safe_load((MODEL_DIR / f"{model}.yaml").read_text(encoding="utf-8"))


def test_september_model_facts() -> None:
    fable = _schema("claude-fable-5-1")
    gemini = _schema("gemini-3.8-flash")
    doubao = _schema("doubao-seed-2-0-mini-260428")
    doubao_rules = {rule["name"]: rule for rule in doubao["parameter_rules"]}

    assert fable["model_properties"]["context_size"] == 1_000_000
    assert fable["pricing"]["input"] == "11.00"
    assert fable["pricing"]["output"] == "55.00"
    assert gemini["model_properties"]["context_size"] == 1_048_576
    assert gemini["pricing"]["input"] == "0.75"
    assert gemini["pricing"]["output"] == "3.75"
    assert doubao["model_properties"]["context_size"] == 256_000
    assert doubao_rules["max_tokens"]["max"] == 32_000
    assert doubao["pricing"]["input"] == "0.0282"
    assert doubao["pricing"]["output"] == "0.282"


def test_fable_5_1_cache_read_multiplier() -> None:
    llm = AnthropicLargeLanguageModel()

    assert llm._cache_read_multiplier("claude-fable-5-1") == 0.025
    assert llm._cache_read_multiplier("claude-fable-5") == 0.1
    assert (
        PromptCachingHandler.calc_adjusted_prompt_tokens(
            1000,
            cache_read_input_tokens=109,
            cache_read_multiplier=llm._cache_read_multiplier("claude-fable-5-1"),
        )
        == 1002
    )


def test_gemini_3_8_flash_omits_sampling_and_prefill() -> None:
    assert "gemini-3.8-flash" in NO_SAMPLING_OR_PREFILL_MODELS
