"""Unit tests for Claude 5 parameter conversion and region resolution in llm.py.

Imports models.llm.llm as a namespace package (requires dify_plugin from the
plugin venv — run via `uv run`). Pure methods are exercised without
instantiating the model class.
"""
import importlib

import pytest

llm_mod = importlib.import_module("models.llm.llm")
model_ids = importlib.import_module("models.llm.model_ids")

BedrockLLM = llm_mod.BedrockLargeLanguageModel


class TestEffortConversion:
    def _convert(self, params, stop=None):
        # The method never touches self — call unbound with None.
        return BedrockLLM._convert_converse_api_model_parameters(None, params, stop)

    def test_effort_maps_to_adaptive_thinking_and_output_config(self):
        inference_config, additional = self._convert(
            {"max_tokens": 4096, "effort": "xhigh"}
        )
        assert additional["thinking"] == {"type": "adaptive"}
        assert additional["output_config"] == {"effort": "xhigh"}
        assert inference_config["maxTokens"] == 4096
        # Claude 5 yaml never exposes sampling params; nothing must leak in
        assert "temperature" not in inference_config
        assert "topP" not in inference_config

    def test_no_effort_no_thinking_injection(self):
        # Other families don't send effort — their fields must be untouched
        inference_config, additional = self._convert(
            {"max_tokens": 1024, "temperature": 0.5}
        )
        assert "thinking" not in additional
        assert "output_config" not in additional
        assert inference_config["temperature"] == 0.5

    def test_effort_with_legacy_reasoning_ignores_reasoning(self):
        # Defensive: if both ever arrive, effort (Claude 5) wins and the
        # legacy budget config must not be emitted alongside it.
        _, additional = self._convert(
            {"max_tokens": 4096, "effort": "high", "reasoning_type": True,
             "reasoning_budget": 2048}
        )
        assert additional["thinking"] == {"type": "adaptive"}
        assert "reasoning_config" not in additional

    def test_effort_drops_sampling_params(self):
        # Claude 5 rejects non-default sampling params; if a caller bypasses
        # the yaml surface and sends them alongside effort, they must be dropped.
        inference_config, additional = self._convert(
            {"max_tokens": 4096, "effort": "high", "temperature": 0.7,
             "top_p": 0.9, "top_k": 40}
        )
        assert "temperature" not in inference_config
        assert "topP" not in inference_config
        assert "top_k" not in additional
        assert additional["thinking"] == {"type": "adaptive"}


class TestClaude5FamilyYamlSurface:
    def test_structured_output_params_not_exposed(self):
        # Live-verified: Opus 5 / Sonnet 5 reject Converse
        # outputConfig.textFormat ("output_config.format: Extra inputs are not
        # permitted") and reject the prefill-based response_format fallback.
        # Neither parameter may appear on the Claude 5 family yaml.
        import yaml
        from pathlib import Path
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "models" / "llm" / "anthropic-claude-5.yaml"
        )
        schema = yaml.safe_load(yaml_path.read_text())
        param_names = {r["name"] for r in schema["parameter_rules"]}
        assert "json_schema" not in param_names
        assert "response_format" not in param_names
        # sampling params stay unexposed too
        assert not {"temperature", "top_p", "top_k"} & param_names


class TestClaude5RegionResolutionInGetModelInfo:
    def _get_model_info(self, model_name, cross_region, region):
        params = {"model_name": model_name, "cross-region": cross_region}
        credentials = {"aws_region": region}
        return BedrockLLM._get_model_info(None, "anthropic claude 5", credentials, params), params

    def test_global_resolution(self):
        info, _ = self._get_model_info("Sonnet 5", "global", "eu-central-1")
        assert info["model"] == "global.anthropic.claude-sonnet-5"
        assert info["support_tool_use"] is True

    def test_opus5_global_resolution(self):
        info, _ = self._get_model_info("Opus 5", "global", "ap-northeast-1")
        assert info["model"] == "global.anthropic.claude-opus-5"

    def test_geographic_us(self):
        info, _ = self._get_model_info("Fable 5", "geographic", "us-west-2")
        assert info["model"] == "us.anthropic.claude-fable-5"

    def test_opus5_geographic_eu(self):
        # Opus 5 / Sonnet 5 have eu. geo profiles (live-verified)
        info, _ = self._get_model_info("Opus 5", "geographic", "eu-central-1")
        assert info["model"] == "eu.anthropic.claude-opus-5"

    @pytest.mark.parametrize("model_name,expected", [
        ("Opus 5", "au.anthropic.claude-opus-5"),
        ("Sonnet 5", "au.anthropic.claude-sonnet-5"),
    ])
    def test_au_profile_resolves_through_converse_route(self, model_name, expected):
        # Integration guard: the au. profile ID must not only resolve but also
        # match a CONVERSE_API_ENABLED_MODEL_INFO prefix — otherwise
        # _get_model_info returns None and _invoke falls back to the legacy
        # bare-ID path, which Claude 5 models reject (profile-only).
        info, _ = self._get_model_info(model_name, "geographic", "ap-southeast-2")
        assert info is not None
        assert info["model"] == expected
        assert info["support_tool_use"] is True

    def test_geographic_eu_raises_actionable_error_for_fable5(self):
        # Fable 5 has no eu. geo profile — only us. and global.
        with pytest.raises(llm_mod.InvokeError, match="global"):
            self._get_model_info("Fable 5", "geographic", "eu-central-1")

    def test_cross_region_param_is_consumed(self):
        _, params = self._get_model_info("Sonnet 5", "global", "us-east-1")
        assert "cross-region" not in params
