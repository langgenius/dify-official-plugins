"""L2 offline tests: _set_orca_extra_body wraps fallback params into extra_body.

OrcaRouter server expects request body to contain a top-level
`extra_body: {models: [...], route: "fallback"}` key. This test verifies our
llm.py method correctly pops the Dify-side parameter names
(`orcarouter_fallback_models` + `orcarouter_route`) and assembles `extra_body`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.llm.llm import OrcaRouterLargeLanguageModel


class TestSetOrcaExtraBody(unittest.TestCase):
    def test_no_params_no_extra_body(self) -> None:
        params: dict = {"temperature": 0.5}
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertNotIn("extra_body", params)
        self.assertEqual(params, {"temperature": 0.5})

    def test_fallback_models_only(self) -> None:
        params = {
            "temperature": 0.5,
            "orcarouter_fallback_models": '["openai/gpt-4o-mini", "openai/gpt-4o"]',
        }
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertNotIn("orcarouter_fallback_models", params)
        self.assertEqual(
            params["extra_body"],
            {"models": ["openai/gpt-4o-mini", "openai/gpt-4o"]},
        )

    def test_route_only(self) -> None:
        params = {"orcarouter_route": "fallback"}
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertNotIn("orcarouter_route", params)
        self.assertEqual(params["extra_body"], {"route": "fallback"})

    def test_both_fallback_and_route(self) -> None:
        params = {
            "orcarouter_fallback_models": '["a/b", "c/d"]',
            "orcarouter_route": "fallback",
        }
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertEqual(
            params["extra_body"],
            {"models": ["a/b", "c/d"], "route": "fallback"},
        )
        self.assertNotIn("orcarouter_fallback_models", params)
        self.assertNotIn("orcarouter_route", params)

    def test_invalid_json_silently_ignored(self) -> None:
        params = {"orcarouter_fallback_models": "not valid json"}
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertNotIn("extra_body", params)
        self.assertNotIn("orcarouter_fallback_models", params)

    def test_empty_string_ignored(self) -> None:
        params = {"orcarouter_fallback_models": "", "orcarouter_route": ""}
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertNotIn("extra_body", params)

    def test_non_list_json_ignored(self) -> None:
        params = {"orcarouter_fallback_models": '"a single string"'}
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertNotIn("extra_body", params)

    def test_filters_empty_model_names(self) -> None:
        params = {"orcarouter_fallback_models": '["a/b", "", null, "c/d"]'}
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertEqual(params["extra_body"]["models"], ["a/b", "c/d"])

    def test_unknown_route_value_dropped(self) -> None:
        # Server only accepts 'fallback' currently
        params = {"orcarouter_route": "loadbalance"}
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertNotIn("extra_body", params)

    def test_preserves_existing_extra_body(self) -> None:
        params = {
            "extra_body": {"custom_key": "preserved"},
            "orcarouter_route": "fallback",
        }
        OrcaRouterLargeLanguageModel._set_orca_extra_body(params)
        self.assertEqual(
            params["extra_body"], {"custom_key": "preserved", "route": "fallback"}
        )


class TestSetReasoningParams(unittest.TestCase):
    def test_no_params_no_reasoning(self) -> None:
        params: dict = {"temperature": 0.5}
        OrcaRouterLargeLanguageModel._set_reasoning_params("openai/gpt-4o", params)
        self.assertNotIn("reasoning_effort", params)
        self.assertNotIn("thinking", params)

    def test_anthropic_enable_thinking_emits_native_block(self) -> None:
        params = {"enable_thinking": True, "reasoning_budget": 2000}
        OrcaRouterLargeLanguageModel._set_reasoning_params(
            "anthropic/claude-opus-4.7", params
        )
        self.assertEqual(
            params["thinking"], {"type": "enabled", "budget_tokens": 2000}
        )
        self.assertNotIn("enable_thinking", params)
        self.assertNotIn("reasoning_budget", params)

    def test_anthropic_thinking_disabled_no_block(self) -> None:
        params = {"enable_thinking": False, "reasoning_budget": 2000}
        OrcaRouterLargeLanguageModel._set_reasoning_params(
            "anthropic/claude-opus-4.7", params
        )
        self.assertNotIn("thinking", params)

    def test_openai_reasoning_effort_flat(self) -> None:
        params = {"reasoning_effort": "high"}
        OrcaRouterLargeLanguageModel._set_reasoning_params("openai/gpt-5", params)
        self.assertEqual(params["reasoning_effort"], "high")
        self.assertNotIn("thinking", params)
        self.assertNotIn("reasoning", params)

    def test_anthropic_ignores_reasoning_effort(self) -> None:
        """Anthropic models don't use reasoning_effort — only thinking block."""
        params = {"reasoning_effort": "high"}
        OrcaRouterLargeLanguageModel._set_reasoning_params(
            "anthropic/claude-opus-4.7", params
        )
        self.assertNotIn("reasoning_effort", params)

    def test_exclude_reasoning_tokens_emits_include_reasoning(self) -> None:
        params = {"exclude_reasoning_tokens": True}
        OrcaRouterLargeLanguageModel._set_reasoning_params("openai/gpt-5", params)
        self.assertEqual(params["include_reasoning"], False)

        params = {"exclude_reasoning_tokens": False}
        OrcaRouterLargeLanguageModel._set_reasoning_params("openai/gpt-5", params)
        self.assertEqual(params["include_reasoning"], True)

    def test_invalid_effort_dropped(self) -> None:
        params = {"reasoning_effort": "ultra-high"}
        OrcaRouterLargeLanguageModel._set_reasoning_params("openai/gpt-5", params)
        self.assertNotIn("reasoning_effort", params)


if __name__ == "__main__":
    unittest.main()
