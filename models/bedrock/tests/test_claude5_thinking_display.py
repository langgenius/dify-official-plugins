"""Unit tests for the Claude 5 `thinking_display` parameter.

`thinking_display=summarized` makes adaptive thinking stream reasoning
summaries, so long thinking does not leave the connection idle.
"""
import importlib
from pathlib import Path

import pytest
import yaml

llm_mod = importlib.import_module("models.llm.llm")
BedrockLLM = llm_mod.BedrockLargeLanguageModel

YAML_PATH = (
    Path(__file__).resolve().parent.parent
    / "models" / "llm" / "anthropic-claude-5.yaml"
)


def _convert(params, stop=None):
    # The method never touches self — call unbound with None.
    return BedrockLLM._convert_converse_api_model_parameters(None, params, stop)


class TestThinkingDisplayConversion:
    def test_effort_without_display_is_unchanged(self):
        # Must be identical to the request sent before thinking_display existed.
        inference_config, additional = _convert({"max_tokens": 4096, "effort": "high"})
        assert additional == {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
        }
        assert inference_config == {"maxTokens": 4096}

    def test_effort_with_omitted_has_no_display(self):
        inference_config, additional = _convert(
            {"max_tokens": 4096, "effort": "high", "thinking_display": "omitted"}
        )
        assert additional == {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
        }
        assert inference_config == {"maxTokens": 4096}

    def test_effort_with_summarized_sets_display(self):
        _, additional = _convert(
            {"max_tokens": 4096, "effort": "xhigh", "thinking_display": "summarized"}
        )
        assert additional["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert additional["output_config"] == {"effort": "xhigh"}

    def test_summarized_without_effort_sends_thinking_only(self):
        inference_config, additional = _convert(
            {"max_tokens": 4096, "thinking_display": "summarized"}
        )
        assert additional == {"thinking": {"type": "adaptive", "display": "summarized"}}
        assert "output_config" not in additional
        assert inference_config == {"maxTokens": 4096}

    def test_summarized_without_effort_drops_sampling_params(self):
        inference_config, additional = _convert(
            {"max_tokens": 4096, "thinking_display": "summarized",
             "temperature": 0.7, "top_p": 0.9, "top_k": 40}
        )
        assert "temperature" not in inference_config
        assert "topP" not in inference_config
        assert "top_k" not in additional
        assert additional["thinking"]["display"] == "summarized"

    def test_summarized_without_effort_ignores_legacy_reasoning(self):
        _, additional = _convert(
            {"max_tokens": 4096, "thinking_display": "summarized",
             "reasoning_type": True, "reasoning_budget": 2048}
        )
        assert "reasoning_config" not in additional

    @pytest.mark.parametrize("params", [
        {"max_tokens": 1024},
        {"max_tokens": 1024, "thinking_display": "omitted"},
    ])
    def test_no_effort_and_not_summarized_sends_no_thinking(self, params):
        inference_config, additional = _convert(params)
        assert "thinking" not in additional
        assert "output_config" not in additional
        assert inference_config == {"maxTokens": 1024}

    @pytest.mark.parametrize("display", ["omitted", "summarized"])
    @pytest.mark.parametrize("with_effort", [True, False])
    def test_display_does_not_leak(self, display, with_effort):
        params = {"max_tokens": 1024, "thinking_display": display}
        if with_effort:
            params["effort"] = "high"
        inference_config, additional = _convert(params, stop=["END"])
        assert "thinking_display" not in inference_config
        assert "thinking_display" not in additional
        assert "thinkingDisplay" not in inference_config
        assert "thinkingDisplay" not in additional
        # The only place `display` may appear is inside `thinking`.
        assert {k for k in additional if k != "thinking"} <= {"output_config"}


class TestThinkingDisplayYaml:
    def _rule(self):
        schema = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
        rules = {r["name"]: r for r in schema["parameter_rules"]}
        return rules["thinking_display"], list(rules)

    def test_rule_definition(self):
        rule, _ = self._rule()
        assert rule["type"] == "string"
        assert rule["required"] is False
        assert rule["default"] == "omitted"
        assert rule["options"] == ["omitted", "summarized"]
        assert {"zh_Hans", "en_US"} <= set(rule["label"])
        assert {"zh_Hans", "en_US"} <= set(rule["help"])

    def test_placed_right_after_effort(self):
        _, names = self._rule()
        assert names.index("thinking_display") == names.index("effort") + 1


class TestFallbackKeepsThinkingDisplay:
    def test_fallback_inputs_pass_additional_fields_through(self):
        # Opus 4.8 also accepts adaptive thinking with display, so the request
        # fields are forwarded unchanged to the refusal-fallback call.
        _, additional = _convert({"max_tokens": 4096, "thinking_display": "summarized"})
        parameters = {
            "modelId": "global.anthropic.claude-fable-5",
            "additionalModelResponseFieldPaths": ["/stop_details"],
            "additionalModelRequestFields": additional,
        }
        credentials = {"aws_region": "us-east-1", "model_parameters": {"model_name": "Fable 5"}}
        fb_params, _, _ = BedrockLLM._claude5_fallback_call_inputs(parameters, credentials)
        assert fb_params["additionalModelRequestFields"] == {
            "thinking": {"type": "adaptive", "display": "summarized"}
        }
