"""End-to-end test: run the packaged plugin with the dify CLI and call real upstreams.

Configure both tiers through environment variables, for any compatible endpoint:

    SWITCHYARD_{CAPABLE,EFFICIENT}_ENDPOINT_URL   base URL ending in /v1
    SWITCHYARD_{CAPABLE,EFFICIENT}_API_KEY        optional
    SWITCHYARD_{CAPABLE,EFFICIENT}_MODEL
    SWITCHYARD_{CAPABLE,EFFICIENT}_API_FORMAT     responses (default) or chat_completions
"""

import os
from pathlib import Path

import pytest
from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeLLMRequest,
    ModelValidateModelCredentialsRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import PromptMessage
from dify_plugin.integration.run import PluginRunner
from pydantic import BaseModel, SerializeAsAny

TIERS = ("capable", "efficient")
# CI passes the built package; locally, build from the plugin source directory.
PLUGIN_PATH = os.getenv("PLUGIN_FILE_PATH") or str(Path(__file__).parent.parent)


class ValidateResult(BaseModel):
    result: bool


class LLMRequest(ModelInvokeLLMRequest):
    # The SDK field is list[PromptMessage], which drops tool_call_id and tool_calls when the
    # test harness serializes the request. Dify itself sends raw JSON, so it is unaffected.
    prompt_messages: list[SerializeAsAny[PromptMessage]]


def _credentials() -> dict:
    credentials = {"picker": "efficient_first", "confidence_threshold": "0.5"}
    for tier in TIERS:
        prefix = f"SWITCHYARD_{tier.upper()}_"
        credentials |= {
            f"{tier}_endpoint_url": os.environ.get(prefix + "ENDPOINT_URL", ""),
            f"{tier}_api_key": os.environ.get(prefix + "API_KEY", ""),
            f"{tier}_model": os.environ.get(prefix + "MODEL", ""),
            f"{tier}_api_format": os.environ.get(prefix + "API_FORMAT", "responses"),
        }
    return credentials


CREDENTIALS = _credentials()
pytestmark = pytest.mark.skipif(
    not all(CREDENTIALS[f"{tier}_{key}"] for tier in TIERS for key in ("endpoint_url", "model")),
    reason="SWITCHYARD_* upstream environment variables are not set",
)

TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
    }
]
TRACEBACK = "Traceback (most recent call last):\nImportError: no module named foo"


def _tool_turn(call_id: str, output: str) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command": "python app.py"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": call_id, "content": output},
    ]


CASES = {
    "plain_chat_stays_efficient": (
        [{"role": "user", "content": "In one sentence: what is a mutex?"}],
        "efficient",
    ),
    "repeated_error_escalates": (
        [
            {"role": "user", "content": "Run the app. If it fails, explain the fix in one sentence."},
            *_tool_turn("c1", TRACEBACK),
            *_tool_turn("c2", TRACEBACK),
        ],
        "capable",
    ),
}


@pytest.mark.parametrize("case", CASES)
def test_invoke_routes_to_expected_tier(case: str) -> None:
    messages, tier = CASES[case]
    payload = LLMRequest(
        user_id="test_user",
        provider="nvidia_nemo_switchyard",
        model_type=ModelType.LLM,
        model="auto",
        credentials=CREDENTIALS,
        prompt_messages=messages,
        model_parameters={"max_tokens": 1024},
        stop=None,
        tools=TOOLS,
        stream=True,
    )
    with PluginRunner(
        config=IntegrationConfig(), plugin_package_path=PLUGIN_PATH
    ) as runner:
        chunks = list(
            runner.invoke(
                access_type=PluginInvokeType.Model,
                access_action=ModelActions.InvokeLLM,
                payload=payload,
                response_type=LLMResultChunk,
            )
        )

    assert chunks, "no chunks returned"
    assert {c.model for c in chunks} == {CREDENTIALS[f"{tier}_model"]}
    assert chunks[-1].delta.finish_reason
    assert any(c.delta.message.content or c.delta.message.tool_calls for c in chunks)


def test_validate_credentials_reports_the_failing_tier() -> None:
    def validate(credentials: dict) -> list[ValidateResult]:
        payload = ModelValidateModelCredentialsRequest(
            user_id="test_user",
            provider="nvidia_nemo_switchyard",
            model_type=ModelType.LLM,
            model="auto",
            credentials=credentials,
        )
        return list(
            runner.invoke(
                access_type=PluginInvokeType.Model,
                access_action=ModelActions.ValidateModelCredentials,
                payload=payload,
                response_type=ValidateResult,
            )
        )

    with PluginRunner(
        config=IntegrationConfig(), plugin_package_path=PLUGIN_PATH
    ) as runner:
        assert [r.result for r in validate(CREDENTIALS)] == [True]
        with pytest.raises(ValueError, match="efficient upstream"):
            validate(CREDENTIALS | {"efficient_api_key": "invalid"})
