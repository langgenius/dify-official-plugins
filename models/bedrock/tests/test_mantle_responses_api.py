"""Unit tests for the bedrock-mantle / OpenAI Responses API path (issue #3651).

The five GPT-5.x mantle models (``openai.gpt-5.6-sol`` / ``-terra`` / ``-luna``,
``openai.gpt-5.5``, ``openai.gpt-5.4``) do NOT go through the standard Converse
API path. They are served by ``https://bedrock-mantle.<region>.api.aws`` via the
OpenAI Responses API, and every method on that dispatch path had no unit-test
coverage before this file:

- ``_is_bedrock_mantle_model`` (the dispatch gate)
- ``_map_openai_exception`` (5-way openai SDK exception mapping)
- ``_get_mantle_auth_token`` (API_Key / Access_Secret_Key / IAM_Role auth)
- ``_build_responses_api_input`` (Dify messages -> Responses input)
- ``_generate_with_responses_api`` (param building, top_p suppression,
  model-name resolution, stream dispatch)
- ``_handle_responses_api_response`` / ``_handle_responses_api_stream``

Conventions follow ``test_legacy_generate_undefined_runtime_client.py``
(PR #3565): ``object.__new__(BedrockLLM)`` for instances, ``MagicMock`` +
``patch`` for clients, exception-class assertions for error paths. No network,
no AWS credentials, no source changes — the methods are correct; these tests
pin them so a future refactor cannot silently alter the behavior.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from dify_plugin.entities.model.llm import LLMUsage

llm_mod = importlib.import_module("models.llm.llm")

BedrockLLM = llm_mod.BedrockLargeLanguageModel

AssistantPromptMessage = llm_mod.AssistantPromptMessage
ImagePromptMessageContent = llm_mod.ImagePromptMessageContent
SystemPromptMessage = llm_mod.SystemPromptMessage
TextPromptMessageContent = llm_mod.TextPromptMessageContent
UserPromptMessage = llm_mod.UserPromptMessage

# (bedrock model id, display name used for pricing) — must stay in sync with
# the elif chain in _generate_with_responses_api and the openai.yaml
# model_name options.
MANTLE_MODELS = [
    ("openai.gpt-5.6-sol", "GPT-5.6 Sol"),
    ("openai.gpt-5.6-terra", "GPT-5.6 Terra"),
    ("openai.gpt-5.6-luna", "GPT-5.6 Luna"),
    ("openai.gpt-5.5", "GPT-5.5"),
    ("openai.gpt-5.4", "GPT-5.4"),
]


# Minimal stand-ins for the openai Responses API stream events. The handlers
# dispatch on type(event).__name__, so the class names are load-bearing.
class ResponseTextDeltaEvent:
    def __init__(self, delta: str = "") -> None:
        self.delta = delta


class ResponseCompletedEvent:
    def __init__(self, response=None) -> None:
        self.response = response


def _make_instance() -> BedrockLLM:
    """Construct a BedrockLargeLanguageModel without the plugin runtime's
    ``__init__`` (mirrors test_legacy_generate_undefined_runtime_client.py).
    """
    return object.__new__(BedrockLLM)


def _make_llm_usage() -> LLMUsage:
    """A minimal valid LLMUsage. LLMResult / LLMResultChunkDelta are pydantic
    models that validate the ``usage`` field, so the mocked
    ``_calc_response_usage`` must return a real instance, not a MagicMock.
    """
    return LLMUsage(
        prompt_tokens=1,
        prompt_unit_price=0.0,
        prompt_price_unit=0.0,
        prompt_price=0.0,
        completion_tokens=2,
        completion_unit_price=0.0,
        completion_price_unit=0.0,
        completion_price=0.0,
        total_tokens=3,
        total_price=0.0,
        currency="USD",
        latency=0.5,
    )


def _make_openai_request() -> httpx.Request:
    return httpx.Request("POST", "https://bedrock-mantle.us-east-2.api.aws/openai/v1")


class TestIsBedrockMantleModel:
    @pytest.mark.parametrize(
        "model_id, _", MANTLE_MODELS, ids=[m[0] for m in MANTLE_MODELS]
    )
    def test_mantle_model_ids_are_in_set(self, model_id: str, _: str) -> None:
        assert BedrockLLM._is_bedrock_mantle_model(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "anthropic.claude-sonnet-5",
            "us.anthropic.claude-sonnet-5",
            "amazon.nova-lite-v1",
            "openai.gpt-5.7-sol",  # not (yet) a mantle model: must NOT match by prefix
        ],
    )
    def test_other_models_are_not_in_set(self, model_id: str) -> None:
        assert BedrockLLM._is_bedrock_mantle_model(model_id) is False

    def test_set_is_exactly_the_five_documented_models(self) -> None:
        # Belt-and-braces: a new mantle model must be added here deliberately
        # (and covered by the tests above), not accidentally.
        assert BedrockLLM._BEDROCK_MANTLE_MODEL_IDS == frozenset(
            m[0] for m in MANTLE_MODELS
        )


class TestMapOpenaiException:
    @pytest.mark.parametrize(
        ("exc_factory", "expected"),
        [
            (
                lambda: openai.APIConnectionError(request=_make_openai_request()),
                llm_mod.InvokeConnectionError,
            ),
            (
                lambda: openai.AuthenticationError(
                    "boom",
                    response=httpx.Response(401, request=_make_openai_request()),
                    body=None,
                ),
                llm_mod.InvokeAuthorizationError,
            ),
            (
                lambda: openai.RateLimitError(
                    "boom",
                    response=httpx.Response(429, request=_make_openai_request()),
                    body=None,
                ),
                llm_mod.InvokeRateLimitError,
            ),
            (
                lambda: openai.BadRequestError(
                    "boom",
                    response=httpx.Response(400, request=_make_openai_request()),
                    body=None,
                ),
                llm_mod.InvokeBadRequestError,
            ),
            (
                lambda: openai.InternalServerError(
                    "boom",
                    response=httpx.Response(500, request=_make_openai_request()),
                    body=None,
                ),
                llm_mod.InvokeServerUnavailableError,
            ),
        ],
        ids=[
            "connection",
            "authentication",
            "rate-limit",
            "bad-request",
            "internal-server",
        ],
    )
    def test_openai_exceptions_map_to_invoke_errors(
        self, exc_factory, expected
    ) -> None:
        with pytest.raises(expected):
            BedrockLLM._map_openai_exception(exc_factory())

    def test_unrecognized_exception_falls_through_to_plain_invoke_error(self) -> None:
        # The fall-through must be InvokeError itself, not a subclass — the
        # caller uses the class to decide retry/error-display behavior.
        with pytest.raises(llm_mod.InvokeError) as exc_info:
            BedrockLLM._map_openai_exception(ValueError("boom"))
        assert type(exc_info.value) is llm_mod.InvokeError
        assert "boom" in str(exc_info.value)


class TestGetMantleAuthToken:
    @staticmethod
    def _fake_token_module() -> MagicMock:
        module = MagicMock(name="aws_bedrock_token_generator")
        module.provide_token = MagicMock(return_value="short-lived-token")
        return module

    def test_api_key_auth_returns_key_directly(self) -> None:
        instance = _make_instance()
        fake = self._fake_token_module()
        with patch.dict(sys.modules, {"aws_bedrock_token_generator": fake}):
            token = instance._get_mantle_auth_token(
                {"auth_method": "API_Key", "bedrock_api_key": "long-term-key"}
            )
        assert token == "long-term-key"
        fake.provide_token.assert_not_called()

    def test_api_key_auth_without_key_raises_bad_request(self) -> None:
        instance = _make_instance()
        with pytest.raises(llm_mod.InvokeBadRequestError, match="bedrock_api_key"):
            instance._get_mantle_auth_token({"auth_method": "API_Key"})

    def test_access_secret_key_auth_generates_botocore_backed_token(self) -> None:
        instance = _make_instance()
        fake = self._fake_token_module()
        credentials = {
            "auth_method": "Access_Secret_Key",
            "aws_region": "us-west-2",
            "aws_access_key_id": "AKIAEXAMPLE",
            "aws_secret_access_key": "secret",
            "aws_session_token": "session",
        }
        with patch.dict(sys.modules, {"aws_bedrock_token_generator": fake}):
            token = instance._get_mantle_auth_token(credentials)
        assert token == "short-lived-token"
        fake.provide_token.assert_called_once()
        kwargs = fake.provide_token.call_args.kwargs
        assert kwargs["region"] == "us-west-2"
        creds = kwargs["aws_credentials_provider"]
        assert creds.access_key == "AKIAEXAMPLE"
        assert creds.secret_key == "secret"
        assert creds.token == "session"

    def test_iam_role_auth_uses_environment_credentials_and_default_region(
        self,
    ) -> None:
        instance = _make_instance()
        fake = self._fake_token_module()
        with patch.dict(sys.modules, {"aws_bedrock_token_generator": fake}):
            token = instance._get_mantle_auth_token({"auth_method": "IAM_Role"})
        assert token == "short-lived-token"
        fake.provide_token.assert_called_once_with(region="us-east-2")

    def test_access_secret_key_missing_keys_fall_back_to_iam_role_path(self) -> None:
        # auth_method=Access_Secret_Key without a key pair must take the
        # environment-credential branch, not raise.
        instance = _make_instance()
        fake = self._fake_token_module()
        with patch.dict(sys.modules, {"aws_bedrock_token_generator": fake}):
            instance._get_mantle_auth_token(
                {"auth_method": "Access_Secret_Key", "aws_region": "us-west-2"}
            )
        fake.provide_token.assert_called_once_with(region="us-west-2")

    def test_missing_token_generator_library_raises_bad_request(self) -> None:
        instance = _make_instance()
        # None in sys.modules makes `from aws_bedrock_token_generator import ...`
        # raise ImportError, simulating the package not being installed.
        with (
            patch.dict(sys.modules, {"aws_bedrock_token_generator": None}),
            pytest.raises(
                llm_mod.InvokeBadRequestError, match="aws-bedrock-token-generator"
            ),
        ):
            instance._get_mantle_auth_token({"auth_method": "IAM_Role"})


class TestBuildResponsesApiInput:
    def test_system_message(self) -> None:
        result = BedrockLLM._build_responses_api_input(
            _make_instance(), [SystemPromptMessage(content="be brief")]
        )
        assert result == [{"role": "system", "content": "be brief"}]

    def test_system_message_none_content_becomes_empty_string(self) -> None:
        result = BedrockLLM._build_responses_api_input(
            _make_instance(), [SystemPromptMessage(content=None)]
        )
        assert result == [{"role": "system", "content": ""}]

    def test_user_text_message(self) -> None:
        result = BedrockLLM._build_responses_api_input(
            _make_instance(), [UserPromptMessage(content="hi")]
        )
        assert result == [{"role": "user", "content": "hi"}]

    def test_user_multimodal_message_joins_text_and_skips_non_text(self) -> None:
        # The mantle path is text-only: text pieces are space-joined in order,
        # any non-text content (here: an image between two text pieces) is
        # dropped rather than raising.
        image = ImagePromptMessageContent(
            data="aGk=", format="png", mime_type="image/png", detail="low"
        )
        result = BedrockLLM._build_responses_api_input(
            _make_instance(),
            [
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="look at"),
                        image,
                        TextPromptMessageContent(data="this"),
                    ]
                )
            ],
        )
        assert result == [{"role": "user", "content": "look at this"}]

    def test_assistant_message_and_none_content(self) -> None:
        result = BedrockLLM._build_responses_api_input(
            _make_instance(), [AssistantPromptMessage(content=None)]
        )
        assert result == [{"role": "assistant", "content": ""}]

    def test_empty_input_yields_empty_list(self) -> None:
        assert BedrockLLM._build_responses_api_input(_make_instance(), []) == []


class TestGenerateWithResponsesApi:
    @staticmethod
    def _make_instance() -> BedrockLLM:
        instance = _make_instance()
        instance._get_mantle_auth_token = MagicMock(return_value="mantle-token")
        instance._handle_responses_api_response = MagicMock(return_value="NON_STREAM")
        instance._handle_responses_api_stream = MagicMock(return_value="STREAM")
        return instance

    @staticmethod
    def _invoke(
        instance: BedrockLLM,
        *,
        model_id: str = "openai.gpt-5.5",
        credentials: dict | None = None,
        model_parameters: dict | None = None,
        prompt_messages: list | None = None,
        stream: bool = False,
    ):
        mock_client = MagicMock(name="openai_client")
        with patch("openai.OpenAI", return_value=mock_client) as openai_ctor:
            result = instance._generate_with_responses_api(
                model_id=model_id,
                credentials=credentials
                if credentials is not None
                else {"aws_region": "us-west-2"},
                prompt_messages=(
                    prompt_messages
                    if prompt_messages is not None
                    else [UserPromptMessage(content="hi")]
                ),
                model_parameters=model_parameters
                if model_parameters is not None
                else {},
                stop=None,
                stream=stream,
                user=None,
            )
        return result, openai_ctor, mock_client

    def test_openai_client_uses_mantle_base_url_and_auth_token(self) -> None:
        instance = self._make_instance()
        _, openai_ctor, _ = self._invoke(instance)
        instance._get_mantle_auth_token.assert_called_once_with(
            {"aws_region": "us-west-2"}
        )
        openai_ctor.assert_called_once_with(
            api_key="mantle-token",
            base_url="https://bedrock-mantle.us-west-2.api.aws/openai/v1",
        )

    def test_mantle_base_url_defaults_to_us_east_2_region(self) -> None:
        instance = self._make_instance()
        _, openai_ctor, _ = self._invoke(instance, credentials={})
        assert openai_ctor.call_args.kwargs["base_url"] == (
            "https://bedrock-mantle.us-east-2.api.aws/openai/v1"
        )

    def test_base_params_and_stop_user_not_forwarded(self) -> None:
        instance = self._make_instance()
        _, _, mock_client = self._invoke(instance)
        kwargs = mock_client.responses.create.call_args.kwargs
        assert kwargs["model"] == "openai.gpt-5.5"
        assert kwargs["input"] == [{"role": "user", "content": "hi"}]
        assert kwargs["stream"] is False
        assert "stop" not in kwargs
        assert "user" not in kwargs

    def test_max_tokens_is_mapped_to_max_output_tokens(self) -> None:
        _, _, mock_client = self._invoke(
            self._make_instance(), model_parameters={"max_tokens": 512}
        )
        kwargs = mock_client.responses.create.call_args.kwargs
        assert kwargs["max_output_tokens"] == 512
        assert "max_tokens" not in kwargs

    def test_temperature_is_forwarded(self) -> None:
        _, _, mock_client = self._invoke(
            self._make_instance(), model_parameters={"temperature": 0.7}
        )
        assert mock_client.responses.create.call_args.kwargs["temperature"] == 0.7

    @pytest.mark.parametrize(
        "model_id, _", MANTLE_MODELS, ids=[m[0] for m in MANTLE_MODELS]
    )
    def test_top_p_is_suppressed_for_every_mantle_model(
        self, model_id: str, _: str
    ) -> None:
        # GPT-5.5/5.6 reject top_p outright and GPT-5.4 rejects it once
        # reasoning is active — the mantle path must never forward it.
        _, _, mock_client = self._invoke(
            self._make_instance(), model_id=model_id, model_parameters={"top_p": 0.9}
        )
        assert "top_p" not in mock_client.responses.create.call_args.kwargs

    def test_converse_only_and_response_format_params_are_dropped(self) -> None:
        _, _, mock_client = self._invoke(
            self._make_instance(),
            model_parameters={
                "cross-region": "global",
                "system_cache_checkpoint": True,
                "latest_two_messages_cache_checkpoint": True,
                "response_format": "json",
            },
        )
        kwargs = mock_client.responses.create.call_args.kwargs
        for key in (
            "cross-region",
            "system_cache_checkpoint",
            "latest_two_messages_cache_checkpoint",
            "response_format",
        ):
            assert key not in kwargs

    def test_caller_model_parameters_dict_is_not_mutated(self) -> None:
        # Retry mechanisms reuse the caller's dict; the copy must be preserved.
        model_parameters = {"max_tokens": 64, "top_p": 0.9, "response_format": "json"}
        self._invoke(self._make_instance(), model_parameters=model_parameters)
        assert model_parameters == {
            "max_tokens": 64,
            "top_p": 0.9,
            "response_format": "json",
        }

    def test_reasoning_effort_becomes_reasoning_block(self) -> None:
        _, _, mock_client = self._invoke(
            self._make_instance(), model_parameters={"reasoning_effort": "high"}
        )
        kwargs = mock_client.responses.create.call_args.kwargs
        assert kwargs["reasoning"] == {"effort": "high"}

    def test_no_reasoning_block_without_reasoning_effort(self) -> None:
        _, _, mock_client = self._invoke(self._make_instance())
        assert "reasoning" not in mock_client.responses.create.call_args.kwargs

    @pytest.mark.parametrize(
        ("model_id", "expected_name"),
        MANTLE_MODELS,
        ids=[m[0] for m in MANTLE_MODELS],
    )
    def test_model_name_resolved_from_model_id_for_pricing(
        self, model_id: str, expected_name: str
    ) -> None:
        instance = self._make_instance()
        self._invoke(instance, model_id=model_id)
        pricing_credentials = instance._handle_responses_api_response.call_args[0][1]
        assert pricing_credentials["model_parameters"]["model_name"] == expected_name

    def test_explicit_model_name_overrides_resolution(self) -> None:
        instance = self._make_instance()
        self._invoke(instance, model_parameters={"model_name": "Custom Billing Name"})
        pricing_credentials = instance._handle_responses_api_response.call_args[0][1]
        assert (
            pricing_credentials["model_parameters"]["model_name"]
            == "Custom Billing Name"
        )

    def test_unknown_model_id_falls_through_to_gpt_5_4_pricing(self) -> None:
        # Known (documented) behavior of the elif chain; a future model id
        # must be added to the chain or it will be priced as GPT-5.4.
        instance = self._make_instance()
        self._invoke(instance, model_id="openai.gpt-5.6-orb")
        pricing_credentials = instance._handle_responses_api_response.call_args[0][1]
        assert pricing_credentials["model_parameters"]["model_name"] == "GPT-5.4"

    def test_existing_pricing_model_parameters_are_preserved(self) -> None:
        instance = self._make_instance()
        self._invoke(
            instance,
            credentials={"aws_region": "us-west-2", "model_parameters": {"keep": 1}},
        )
        pricing_credentials = instance._handle_responses_api_response.call_args[0][1]
        assert pricing_credentials["model_parameters"] == {
            "keep": 1,
            "model_name": "GPT-5.5",
        }

    def test_stream_true_dispatches_to_stream_handler(self) -> None:
        instance = self._make_instance()
        result, _, mock_client = self._invoke(instance, stream=True)
        assert result == "STREAM"
        instance._handle_responses_api_stream.assert_called_once()
        instance._handle_responses_api_response.assert_not_called()
        # stream flag is forwarded to the API
        assert mock_client.responses.create.call_args.kwargs["stream"] is True

    def test_stream_false_dispatches_to_non_stream_handler(self) -> None:
        instance = self._make_instance()
        result, _, _ = self._invoke(instance, stream=False)
        assert result == "NON_STREAM"
        instance._handle_responses_api_response.assert_called_once()
        instance._handle_responses_api_stream.assert_not_called()

    def test_missing_openai_package_raises_bad_request(self) -> None:
        instance = self._make_instance()
        with (
            patch.dict(sys.modules, {"openai": None}),
            pytest.raises(llm_mod.InvokeBadRequestError, match="pip install openai"),
        ):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-west-2"},
                prompt_messages=[UserPromptMessage(content="hi")],
                model_parameters={},
                stop=None,
                stream=False,
                user=None,
            )

    def test_client_exception_is_mapped_to_invoke_error(self) -> None:
        instance = self._make_instance()
        error = openai.BadRequestError(
            "unsupported_parameter",
            response=httpx.Response(400, request=_make_openai_request()),
            body=None,
        )
        mock_client = MagicMock(name="openai_client")
        mock_client.responses.create.side_effect = error
        with (
            patch("openai.OpenAI", return_value=mock_client),
            pytest.raises(llm_mod.InvokeBadRequestError),
        ):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-west-2"},
                prompt_messages=[UserPromptMessage(content="hi")],
                model_parameters={},
                stop=None,
                stream=False,
                user=None,
            )


class TestHandleResponsesApiResponse:
    @staticmethod
    def _make_instance() -> tuple[BedrockLLM, LLMUsage]:
        instance = _make_instance()
        usage = _make_llm_usage()
        instance._calc_response_usage = MagicMock(return_value=usage)
        return instance, usage

    def test_builds_llm_result_with_usage(self) -> None:
        instance, usage = self._make_instance()
        response = SimpleNamespace(
            output_text="Hello!",
            usage=SimpleNamespace(input_tokens=3, output_tokens=5),
        )
        messages = [UserPromptMessage(content="hi")]
        result = instance._handle_responses_api_response(
            "openai.gpt-5.5", {"aws_region": "us-west-2"}, response, messages
        )
        assert isinstance(result, llm_mod.LLMResult)
        assert result.model == "openai.gpt-5.5"
        assert result.message.content == "Hello!"
        assert result.usage is usage
        instance._calc_response_usage.assert_called_once_with(
            "openai.gpt-5.5", {"aws_region": "us-west-2"}, 3, 5
        )

    def test_missing_usage_and_text_default_to_zero_and_empty(self) -> None:
        instance, _ = self._make_instance()
        response = SimpleNamespace(output_text=None, usage=None)
        result = instance._handle_responses_api_response(
            "openai.gpt-5.4", {}, response, []
        )
        assert result.message.content == ""
        instance._calc_response_usage.assert_called_once_with(
            "openai.gpt-5.4", {}, 0, 0
        )


class TestHandleResponsesApiStream:
    @staticmethod
    def _make_instance() -> tuple[BedrockLLM, LLMUsage]:
        instance = _make_instance()
        usage = _make_llm_usage()
        instance._calc_response_usage = MagicMock(return_value=usage)
        return instance, usage

    @staticmethod
    def _completed(input_tokens: int, output_tokens: int) -> ResponseCompletedEvent:
        return ResponseCompletedEvent(
            response=SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=input_tokens, output_tokens=output_tokens
                )
            )
        )

    def test_text_deltas_yield_indexed_chunks(self) -> None:
        instance, _ = self._make_instance()
        chunks = list(
            instance._handle_responses_api_stream(
                "openai.gpt-5.5",
                {},
                [ResponseTextDeltaEvent("He"), ResponseTextDeltaEvent("llo")],
                [],
            )
        )
        assert [c.delta.message.content for c in chunks] == ["He", "llo"]
        assert [c.delta.index for c in chunks] == [0, 1]

    def test_completed_event_yields_final_chunk_with_usage(self) -> None:
        instance, usage = self._make_instance()
        chunks = list(
            instance._handle_responses_api_stream(
                "openai.gpt-5.5",
                {"aws_region": "us-west-2"},
                [ResponseTextDeltaEvent("Hi"), self._completed(3, 5)],
                [],
            )
        )
        assert len(chunks) == 2
        final = chunks[-1]
        assert final.delta.finish_reason == "stop"
        assert final.delta.message.content == ""
        assert final.delta.usage is usage
        assert final.delta.index == 1  # counted from the yielded delta, not the event
        instance._calc_response_usage.assert_called_once_with(
            "openai.gpt-5.5", {"aws_region": "us-west-2"}, 3, 5
        )

    def test_empty_deltas_and_unknown_events_are_skipped(self) -> None:
        instance, _ = self._make_instance()
        chunks = list(
            instance._handle_responses_api_stream(
                "openai.gpt-5.5",
                {},
                [
                    ResponseTextDeltaEvent(""),
                    SimpleNamespace(),  # any non-delta, non-completed event
                    ResponseTextDeltaEvent("x"),
                    ResponseCompletedEvent(response=None),  # no usage on response
                ],
                [],
            )
        )
        # Only "x" produced a delta chunk; the completed event still closes
        # the stream, with usage falling back to 0/0.
        assert [c.delta.message.content for c in chunks] == ["x", ""]
        assert chunks[-1].delta.finish_reason == "stop"
        instance._calc_response_usage.assert_called_once_with(
            "openai.gpt-5.5", {}, 0, 0
        )
