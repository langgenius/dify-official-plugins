"""Regression tests for TongyiProvider.validate_provider_credentials.

The provider's credential validation method must:
- accept an optional `validate_model` override in the credentials dict,
- fall back to a sentinel model with broad DashScope availability when no
  override is provided,
- propagate CredentialsValidateFailedError unchanged from the underlying
  model validator,
- propagate unexpected exceptions through the existing exception handler.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.errors.model import CredentialsValidateFailedError

from dashscope.api_entities.dashscope_response import (
    DashScopeAPIResponse,
    MultiModalConversationResponse,
)

# Make the plugin's own modules importable when pytest is invoked from the
# plugin directory or the repo root, matching the pattern in the other
# models/tongyi/tests/ files.
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from provider.tongyi import DEFAULT_VALIDATE_MODEL, TongyiProvider  # noqa: E402
from models.llm.llm import TongyiLargeLanguageModel  # noqa: E402


def _provider() -> TongyiProvider:
    """Construct a TongyiProvider without invoking ModelProvider.__init__,
    which would try to load the provider schema from disk. Stubs the
    attributes the production exception handler reads, so tests can
    exercise the error paths without a real schema.
    """
    provider = object.__new__(TongyiProvider)
    provider.provider_schema = MagicMock()
    provider.provider_schema.provider = "tongyi"
    return provider


def test_default_validate_model_is_qwen38_flash() -> None:
    """Use a current model available in both Beijing and Singapore."""
    assert DEFAULT_VALIDATE_MODEL == "qwen3.8-flash"


def test_default_validate_model_is_in_plugin_catalog() -> None:
    """Sanity check: the default sentinel exists in the plugin's model
    catalog so the validation call can actually run.
    """
    position_file = _PLUGIN_DIR / "models" / "llm" / "_position.yaml"
    assert position_file.exists(), f"missing position file: {position_file}"
    items = yaml.safe_load(position_file.read_text(encoding="utf-8")) or []
    assert DEFAULT_VALIDATE_MODEL in items, (
        f"DEFAULT_VALIDATE_MODEL={DEFAULT_VALIDATE_MODEL!r} not listed in {position_file}"
    )


def test_validate_provider_credentials_uses_default_when_no_override() -> None:
    """When credentials do not include `validate_model`, the provider uses
    the default sentinel.
    """
    provider = _provider()
    fake_instance = MagicMock()
    credentials = {"dashscope_api_key": "test-key"}
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        provider.validate_provider_credentials(credentials=credentials)

    fake_instance.validate_credentials.assert_called_once()
    kwargs = fake_instance.validate_credentials.call_args.kwargs
    assert kwargs["model"] == DEFAULT_VALIDATE_MODEL, (
        f"expected default sentinel {DEFAULT_VALIDATE_MODEL!r}, got {kwargs['model']!r}"
    )
    assert kwargs["credentials"] == credentials


def test_validate_provider_credentials_respects_override() -> None:
    """When credentials include `validate_model`, the provider uses that
    value instead of the default.
    """
    provider = _provider()
    fake_instance = MagicMock()
    override = "qwen3-vl-plus"
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        provider.validate_provider_credentials(
            credentials={"dashscope_api_key": "test-key", "validate_model": override}
        )

    fake_instance.validate_credentials.assert_called_once()
    kwargs = fake_instance.validate_credentials.call_args.kwargs
    assert kwargs["model"] == override, (
        f"expected override {override!r}, got {kwargs['model']!r}"
    )


def test_validate_provider_credentials_treats_empty_override_as_default() -> None:
    """An empty-string `validate_model` falls back to the default rather
    than being passed through to the model validator.
    """
    provider = _provider()
    fake_instance = MagicMock()
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        provider.validate_provider_credentials(
            credentials={"dashscope_api_key": "test-key", "validate_model": ""}
        )

    kwargs = fake_instance.validate_credentials.call_args.kwargs
    assert kwargs["model"] == DEFAULT_VALIDATE_MODEL, (
        f"empty override should fall back to default, got {kwargs['model']!r}"
    )


def test_validate_provider_credentials_propagates_credentials_error() -> None:
    """CredentialsValidateFailedError from the underlying model validator
    is re-raised unchanged.
    """
    provider = _provider()
    fake_instance = MagicMock()
    fake_instance.validate_credentials.side_effect = CredentialsValidateFailedError(
        "invalid api key"
    )
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        with pytest.raises(CredentialsValidateFailedError, match="invalid api key"):
            provider.validate_provider_credentials(
                credentials={"dashscope_api_key": "x"}
            )


def test_validate_provider_credentials_propagates_unexpected_error() -> None:
    """Unexpected exceptions from the underlying model validator are
    caught by the provider's existing handler and re-raised so Dify
    surfaces a generic failure to the user instead of crashing the
    plugin process.
    """
    provider = _provider()
    fake_instance = MagicMock()
    fake_instance.validate_credentials.side_effect = RuntimeError("network down")
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        with pytest.raises(RuntimeError, match="network down"):
            provider.validate_provider_credentials(
                credentials={"dashscope_api_key": "x"}
            )


@pytest.mark.parametrize("return_class", [False, True])
@pytest.mark.parametrize(
    ("endpoint_credentials", "expected_base_address"),
    [
        ({}, "https://dashscope.aliyuncs.com/api/v1"),
        (
            {"use_international_endpoint": "true"},
            "https://dashscope-intl.aliyuncs.com/api/v1",
        ),
        (
            {"api_host": "llm-test.cn-beijing.maas.aliyuncs.com"},
            "https://llm-test.cn-beijing.maas.aliyuncs.com/api/v1",
        ),
    ],
)
@pytest.mark.parametrize("status_code", [200, 401, 404])
def test_default_validation_calls_current_model_and_checks_response(
    return_class, endpoint_credentials, expected_base_address, status_code
) -> None:
    """Exercise the provider through the real LLM validator and response parser.

    A multimodal, non-streaming request must be made with the configured host,
    and invalid credentials/model errors must never be silently accepted.
    """
    schema_path = _PLUGIN_DIR / "models" / "llm" / f"{DEFAULT_VALIDATE_MODEL}.yaml"
    schema = AIModelEntity.model_validate(yaml.safe_load(schema_path.read_text()))
    provider = _provider()
    provider.provider_schema.models = [schema]
    model = TongyiLargeLanguageModel(model_schemas=[schema])
    credentials = {"dashscope_api_key": "test-key", **endpoint_credentials}
    response = MultiModalConversationResponse.from_api_response(
        DashScopeAPIResponse(
            status_code=status_code,
            request_id="test-request",
            code="OK" if status_code == 200 else "TestError",
            message="" if status_code == 200 else "validation rejected",
            output={
                "choices": [
                    {"message": {"role": "assistant", "content": [{"text": "pong"}]}}
                ]
            },
            usage={"input_tokens": 1, "output_tokens": 1},
        )
    )
    with (
        patch.object(
            provider,
            "get_model_instance",
            return_value=TongyiLargeLanguageModel if return_class else model,
        ),
        patch("models.llm.llm.MultiModalConversation.call", return_value=response) as call,
        patch("models.llm.llm.Generation.call") as text_call,
    ):
        if status_code == 200:
            provider.validate_provider_credentials(credentials)
        else:
            with pytest.raises(CredentialsValidateFailedError, match="validation rejected"):
                provider.validate_provider_credentials(credentials)

    call.assert_called_once()
    text_call.assert_not_called()
    kwargs = call.call_args.kwargs
    assert kwargs["model"] == "qwen3.8-flash"
    assert kwargs["base_address"] == expected_base_address
    assert kwargs["api_key"] == "test-key"
    assert kwargs["enable_thinking"] is False
    assert kwargs["stream"] is False
    assert kwargs["messages"] == [{"role": "user", "content": [{"text": "ping"}]}]
