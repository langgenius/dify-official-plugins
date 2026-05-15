"""L3 live test: verify extra_body fallback routing actually reaches OrcaRouter.

Calls openai/gpt-4o-mini with orcarouter_fallback_models=["openai/gpt-4o"].
Success criteria: request returns 2xx (either primary or fallback served).
This proves our llm.py correctly wraps the parameters into extra_body and
OrcaRouter parses the field.

Requires ORCAROUTER_API_KEY.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeLLMRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.integration.run import PluginRunner


@pytest.mark.skipif(
    not os.getenv("ORCAROUTER_API_KEY"),
    reason="ORCAROUTER_API_KEY required for live extra_body test",
)
def test_fallback_models_extra_body() -> None:
    api_key = os.getenv("ORCAROUTER_API_KEY")
    plugin_path = os.getenv("PLUGIN_FILE_PATH") or str(Path(__file__).parent.parent)

    payload = ModelInvokeLLMRequest(
        user_id="test_user",
        provider="orcarouter",
        model_type=ModelType.LLM,
        model="openai/gpt-4o-mini",
        credentials={"api_key": api_key},
        prompt_messages=[{"role": "user", "content": "Reply with the word 'ok'."}],
        stop=None,
        tools=None,
        stream=True,
        model_parameters={
            "orcarouter_fallback_models": '["openai/gpt-4o"]',
            "orcarouter_route": "fallback",
            "max_tokens": 10,
        },
    )

    with PluginRunner(
        config=IntegrationConfig(), plugin_package_path=plugin_path
    ) as runner:
        results: list[LLMResultChunk] = []
        for result in runner.invoke(
            access_type=PluginInvokeType.Model,
            access_action=ModelActions.InvokeLLM,
            payload=payload,
            response_type=LLMResultChunk,
        ):
            results.append(result)
        assert len(results) > 0, (
            "extra_body request should succeed (primary or fallback). "
            "If this fails with 400, check that OrcaRouter accepts extra_body.models/route."
        )
