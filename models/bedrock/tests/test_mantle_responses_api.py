"""Unit tests for the bedrock-mantle / OpenAI Responses API path (GPT-5.x).

Pins the behavior of every method on the mantle dispatch path in
``models/bedrock/models/llm/llm.py`` (lines ~2018-2260), covering:

- ``_is_bedrock_mantle_model`` (the dispatch gate)
- ``_get_mantle_auth_token`` (API_Key / Access_Secret_Key / IAM_Role)
- ``_map_openai_exception`` (5-way exception mapping)
- ``_build_responses_api_input`` (Dify -> OpenAI Responses input)
- ``_generate_with_responses_api`` (param building, top_p suppression,
  model-name resolution)
- ``_handle_responses_api_response`` (non-streaming response formatting)
- ``_handle_responses_api_stream`` (streaming response formatting)

The mantle path is the only LLM family in ``llm.py`` with no prior
test coverage. The five model IDs it covers are ``openai.gpt-5.6-sol``,
``openai.gpt-5.6-terra``, ``openai.gpt-5.6-luna``, ``openai.gpt-5.5``,
and ``openai.gpt-5.4``.

Test pattern follows ``test_legacy_generate_undefined_runtime_client.py``
(PR #3565): ``object.__new__(cls)`` for instance construction,
``unittest.mock`` for client and SDK mocking, exception-class assertions
for error paths.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

llm_mod = importlib.import_module("models.llm.llm")
BedrockLLM = llm_mod.BedrockLargeLanguageModel


def _empty_usage() -> LLMUsage:
    """A real ``LLMUsage`` instance for places where a MagicMock would
    fail pydantic validation on ``LLMResult.usage`` / ``LLMResultChunk.delta.usage``.
    """
    return LLMUsage.empty_usage()


def _make_instance() -> BedrockLLM:
    """Construct a ``BedrockLargeLanguageModel`` without invoking the real
    plugin-runtime ``__init__``. Method-level tests mock the methods they
    exercise, so a bare instance is enough.
    """
    return object.__new__(BedrockLLM)


# ---------------------------------------------------------------------------
# Dispatch gate
# ---------------------------------------------------------------------------


class TestIsBedrockMantleModel:
    """The dispatch gate (line 119 of ``llm.py``) decides whether to
    route to ``_generate_with_responses_api`` or the standard Converse
    API path. A typo in the model_id set would silently fall through
    to Converse and 500 against an incompatible endpoint.
    """

    @pytest.mark.parametrize(
        "model_id",
        [
            "openai.gpt-5.6-sol",
            "openai.gpt-5.6-terra",
            "openai.gpt-5.6-luna",
            "openai.gpt-5.5",
            "openai.gpt-5.4",
        ],
    )
    def test_mantle_model_ids_are_recognized(self, model_id: str) -> None:
        assert BedrockLLM._is_bedrock_mantle_model(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "anthropic.claude-5-opus",
            "cohere.command-r-plus",
            "amazon.nova-pro",
            "openai.gpt-4o",
            "openai.gpt-5.6-aphelion",  # close but not in the set
            "",
        ],
    )
    def test_non_mantle_model_ids_are_rejected(self, model_id: str) -> None:
        assert BedrockLLM._is_bedrock_mantle_model(model_id) is False


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------


class TestMapOpenAIException:
    """Static exception mapper. Each ``openai.*`` exception class must
    map to a distinct ``InvokeError`` subclass, and unrecognised
    exceptions must fall through to ``InvokeError``.
    """

    @staticmethod
    def _patched_openai() -> SimpleNamespace:
        """Build a fake ``openai`` module with all five exception classes
        the production code's ``isinstance`` chain references.

        The production function walks ``openai.APIConnectionError``,
        ``openai.AuthenticationError``, etc. in order and raises on the
        first match. To exercise the fall-through paths, the module
        must expose every class — even when the test only cares about
        one of them. ``SimpleNamespace`` is used (not ``MagicMock``)
        because ``MagicMock.__getattr__`` would auto-create attribute
        access and return a MagicMock instead of the class, breaking
        the ``isinstance`` check.
        """
        return SimpleNamespace(
            APIConnectionError=type("APIConnectionError", (Exception,), {}),
            AuthenticationError=type("AuthenticationError", (Exception,), {}),
            RateLimitError=type("RateLimitError", (Exception,), {}),
            BadRequestError=type("BadRequestError", (Exception,), {}),
            InternalServerError=type("InternalServerError", (Exception,), {}),
        )

    def test_api_connection_error_maps_to_invoke_connection_error(self) -> None:
        fake_openai = self._patched_openai()
        ex = fake_openai.APIConnectionError("conn refused")
        with patch.dict("sys.modules", {"openai": fake_openai}):
            with pytest.raises(InvokeConnectionError):
                BedrockLLM._map_openai_exception(ex)

    def test_authentication_error_maps_to_invoke_authorization_error(self) -> None:
        fake_openai = self._patched_openai()
        ex = fake_openai.AuthenticationError("bad key")
        with patch.dict("sys.modules", {"openai": fake_openai}):
            with pytest.raises(InvokeAuthorizationError):
                BedrockLLM._map_openai_exception(ex)

    def test_rate_limit_error_maps_to_invoke_rate_limit_error(self) -> None:
        fake_openai = self._patched_openai()
        ex = fake_openai.RateLimitError("rate limited")
        with patch.dict("sys.modules", {"openai": fake_openai}):
            with pytest.raises(InvokeRateLimitError):
                BedrockLLM._map_openai_exception(ex)

    def test_bad_request_error_maps_to_invoke_bad_request_error(self) -> None:
        fake_openai = self._patched_openai()
        ex = fake_openai.BadRequestError("bad request")
        with patch.dict("sys.modules", {"openai": fake_openai}):
            with pytest.raises(InvokeBadRequestError):
                BedrockLLM._map_openai_exception(ex)

    def test_internal_server_error_maps_to_invoke_server_unavailable(self) -> None:
        fake_openai = self._patched_openai()
        ex = fake_openai.InternalServerError("upstream 500")
        with patch.dict("sys.modules", {"openai": fake_openai}):
            with pytest.raises(InvokeServerUnavailableError):
                BedrockLLM._map_openai_exception(ex)

    def test_unrecognised_exception_falls_through_to_invoke_error(self) -> None:
        fake_openai = self._patched_openai()
        with patch.dict("sys.modules", {"openai": fake_openai}):
            with pytest.raises(InvokeError):
                BedrockLLM._map_openai_exception(ValueError("not an openai error"))


# ---------------------------------------------------------------------------
# Auth token generation
# ---------------------------------------------------------------------------


class TestGetMantleAuthTokenAPIKey:
    def test_api_key_auth_returns_bedrock_api_key(self) -> None:
        instance = _make_instance()
        creds = {"auth_method": "API_Key", "bedrock_api_key": "sk-abc123"}
        assert instance._get_mantle_auth_token(creds) == "sk-abc123"

    def test_api_key_auth_missing_key_raises(self) -> None:
        instance = _make_instance()
        creds = {"auth_method": "API_Key"}
        with pytest.raises(InvokeBadRequestError, match="bedrock_api_key is required"):
            instance._get_mantle_auth_token(creds)


class TestGetMantleAuthTokenAccessSecretKey:
    def test_access_secret_key_uses_botocore_credentials(self) -> None:
        instance = _make_instance()
        creds = {
            "auth_method": "Access_Secret_Key",
            "aws_access_key_id": "AKIA",
            "aws_secret_access_key": "secret",
            "aws_session_token": "session-token",
            "aws_region": "us-west-2",
        }
        mock_provide_token = MagicMock(return_value="short-lived-token")
        fake_bedrock_token_module = MagicMock(provide_token=mock_provide_token)
        with patch.dict("sys.modules", {"aws_bedrock_token_generator": fake_bedrock_token_module}):
            token = instance._get_mantle_auth_token(creds)
        assert token == "short-lived-token"
        mock_provide_token.assert_called_once()
        kwargs = mock_provide_token.call_args.kwargs
        assert kwargs["region"] == "us-west-2"
        assert kwargs["aws_credentials_provider"] is not None

    def test_access_secret_key_missing_token_generator_raises(self) -> None:
        instance = _make_instance()
        creds = {
            "auth_method": "Access_Secret_Key",
            "aws_access_key_id": "AKIA",
            "aws_secret_access_key": "secret",
        }
        # Force the import inside the function to fail.
        with patch.dict("sys.modules", {"aws_bedrock_token_generator": None}):
            with pytest.raises(
                InvokeBadRequestError, match="aws-bedrock-token-generator is required"
            ):
                instance._get_mantle_auth_token(creds)


class TestGetMantleAuthTokenIAMRole:
    def test_iam_role_calls_provide_token_with_region_only(self) -> None:
        instance = _make_instance()
        creds = {"auth_method": "IAM_Role", "aws_region": "eu-central-1"}
        mock_provide_token = MagicMock(return_value="iam-derived-token")
        fake_bedrock_token_module = MagicMock(provide_token=mock_provide_token)
        with patch.dict("sys.modules", {"aws_bedrock_token_generator": fake_bedrock_token_module}):
            token = instance._get_mantle_auth_token(creds)
        assert token == "iam-derived-token"
        mock_provide_token.assert_called_once_with(region="eu-central-1")


# ---------------------------------------------------------------------------
# Input message conversion
# ---------------------------------------------------------------------------


class TestBuildResponsesApiInput:
    def test_system_user_assistant_converted(self) -> None:
        instance = _make_instance()
        messages = [
            SystemPromptMessage(content="You are helpful."),
            UserPromptMessage(content="What is 2+2?"),
            AssistantPromptMessage(content="4"),
            UserPromptMessage(content="And 3+3?"),
        ]
        result = instance._build_responses_api_input(messages)
        assert result == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "And 3+3?"},
        ]

    def test_user_with_multimodal_content_joins_text_only(self) -> None:
        instance = _make_instance()
        text_part = TextPromptMessageContent(data="describe the image")
        messages = [UserPromptMessage(content=[text_part])]
        result = instance._build_responses_api_input(messages)
        assert result == [{"role": "user", "content": "describe the image"}]

    def test_empty_input_returns_empty_list(self) -> None:
        instance = _make_instance()
        assert instance._build_responses_api_input([]) == []

    def test_system_prompt_empty_content_normalised_to_empty_string(self) -> None:
        instance = _make_instance()
        messages = [SystemPromptMessage(content="")]
        assert instance._build_responses_api_input(messages) == [
            {"role": "system", "content": ""},
        ]


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


class TestGenerateWithResponsesApi:
    """The main flow. We patch ``openai.OpenAI`` via ``sys.modules`` and
    exercise the parameter-building branches. The handle-methods are
    mocked because they are covered in their own test classes.
    """

    @staticmethod
    def _patch_openai_with(client: MagicMock) -> "patch":
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI = MagicMock(return_value=client)
        return patch.dict("sys.modules", {"openai": mock_openai_module})

    @staticmethod
    def _wire_instance(instance: BedrockLLM) -> MagicMock:
        """Mock every collaborator the main flow calls, except the openai
        SDK which the test patches via ``_patch_openai_with``. Returns
        the mock client that ``OpenAI()`` should return.
        """
        instance._get_mantle_auth_token = MagicMock(return_value="t")
        instance._build_responses_api_input = MagicMock(
            return_value=[{"role": "user", "content": "hi"}]
        )
        instance._handle_responses_api_stream = MagicMock(return_value="STREAMED")
        instance._handle_responses_api_response = MagicMock(return_value="NON_STREAMED")
        instance._calc_response_usage = MagicMock(return_value=_empty_usage())
        client = MagicMock(name="openai_client")
        client.responses.create.return_value = "raw"
        return client

    def test_streams_to_handle_responses_api_stream_when_stream_true(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)

        with self._patch_openai_with(client):
            result = instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={},
                stop=None,
                stream=True,
                user=None,
            )

        assert result == "STREAMED"
        instance._handle_responses_api_stream.assert_called_once()
        instance._handle_responses_api_response.assert_not_called()

    def test_returns_to_handle_responses_api_response_when_stream_false(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)

        with self._patch_openai_with(client):
            result = instance._generate_with_responses_api(
                model_id="openai.gpt-5.4",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={},
                stream=False,
                user=None,
            )

        assert result == "NON_STREAMED"
        instance._handle_responses_api_response.assert_called_once()
        instance._handle_responses_api_stream.assert_not_called()

    def test_max_tokens_renamed_to_max_output_tokens(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)

        with self._patch_openai_with(client):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={"max_tokens": 4096},
                stream=False,
                user=None,
            )

        params = mock_client_kwargs(client)
        assert params["max_output_tokens"] == 4096
        assert "max_tokens" not in params

    def test_temperature_forwarded(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)

        with self._patch_openai_with(client):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={"temperature": 0.3},
                stream=False,
                user=None,
            )

        assert mock_client_kwargs(client)["temperature"] == 0.3

    def test_top_p_is_dropped(self) -> None:
        """GPT-5.5/5.6 reject top_p with 400 unsupported_parameter; GPT-5.4
        rejects it once reasoning is active. The builder must drop top_p
        even if the caller supplies it.
        """
        instance = _make_instance()
        client = self._wire_instance(instance)

        with self._patch_openai_with(client):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={"temperature": 0.5, "top_p": 0.9},
                stream=False,
                user=None,
            )

        params = mock_client_kwargs(client)
        assert "top_p" not in params
        assert params["temperature"] == 0.5

    def test_reasoning_effort_wrapped_in_reasoning_block(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)

        with self._patch_openai_with(client):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={"reasoning_effort": "high"},
                stream=False,
                user=None,
            )

        assert mock_client_kwargs(client)["reasoning"] == {"effort": "high"}

    def test_response_format_dropped(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)

        with self._patch_openai_with(client):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={"response_format": "json"},
                stream=False,
                user=None,
            )

        assert "response_format" not in mock_client_kwargs(client)

    @pytest.mark.parametrize(
        "model_id,expected_name",
        [
            ("openai.gpt-5.6-sol", "GPT-5.6 Sol"),
            ("openai.gpt-5.6-terra", "GPT-5.6 Terra"),
            ("openai.gpt-5.6-luna", "GPT-5.6 Luna"),
            ("openai.gpt-5.5", "GPT-5.5"),
            ("openai.gpt-5.4", "GPT-5.4"),
        ],
    )
    def test_model_id_resolves_to_human_readable_name_for_pricing(
        self, model_id: str, expected_name: str
    ) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)
        captured: dict = {}

        def _capture_handler(model, credentials, response, prompt_messages):
            captured.update(credentials)
            return "NON_STREAMED"

        instance._handle_responses_api_response = MagicMock(side_effect=_capture_handler)

        with self._patch_openai_with(client):
            instance._generate_with_responses_api(
                model_id=model_id,
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={},
                stream=False,
                user=None,
            )

        assert captured["model_parameters"]["model_name"] == expected_name

    def test_model_name_override_from_model_parameters(self) -> None:
        """If the caller passes ``model_name`` in ``model_parameters``,
        that overrides the model_id-based resolution.
        """
        instance = _make_instance()
        client = self._wire_instance(instance)
        captured: dict = {}

        def _capture_handler(model, credentials, response, prompt_messages):
            captured.update(credentials)
            return "NON_STREAMED"

        instance._handle_responses_api_response = MagicMock(side_effect=_capture_handler)

        with self._patch_openai_with(client):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "us-east-2"},
                prompt_messages=[],
                model_parameters={"model_name": "Custom Display Name"},
                stream=False,
                user=None,
            )

        assert captured["model_parameters"]["model_name"] == "Custom Display Name"

    def test_base_url_uses_aws_region(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI = MagicMock(return_value=client)

        with patch.dict("sys.modules", {"openai": mock_openai_module}):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={"aws_region": "ap-northeast-1"},
                prompt_messages=[],
                model_parameters={},
                stream=False,
                user=None,
            )

        openai_call_kwargs = mock_openai_module.OpenAI.call_args.kwargs
        assert (
            openai_call_kwargs["base_url"]
            == "https://bedrock-mantle.ap-northeast-1.api.aws/openai/v1"
        )
        assert openai_call_kwargs["api_key"] == "t"

    def test_default_region_is_us_east_2(self) -> None:
        instance = _make_instance()
        client = self._wire_instance(instance)
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI = MagicMock(return_value=client)

        with patch.dict("sys.modules", {"openai": mock_openai_module}):
            instance._generate_with_responses_api(
                model_id="openai.gpt-5.5",
                credentials={},  # no aws_region
                prompt_messages=[],
                model_parameters={},
                stream=False,
                user=None,
            )

        openai_call_kwargs = mock_openai_module.OpenAI.call_args.kwargs
        assert (
            openai_call_kwargs["base_url"] == "https://bedrock-mantle.us-east-2.api.aws/openai/v1"
        )


# ---------------------------------------------------------------------------
# Response handlers
# ---------------------------------------------------------------------------


def mock_client_kwargs(client: MagicMock) -> dict:
    """Return the kwargs of the most recent ``client.responses.create`` call."""
    return client.responses.create.call_args.kwargs


class TestHandleResponsesApiResponse:
    def test_non_streaming_response_builds_llm_result(self) -> None:
        instance = _make_instance()
        instance._calc_response_usage = MagicMock(return_value=_empty_usage())

        response = MagicMock(name="openai_response")
        response.output_text = "Hello, world!"
        response.usage.input_tokens = 10
        response.usage.output_tokens = 5

        result = instance._handle_responses_api_response(
            model="openai.gpt-5.5",
            credentials={"aws_region": "us-east-2"},
            response=response,
            prompt_messages=[],
        )

        assert result.model == "openai.gpt-5.5"
        assert result.message.content == "Hello, world!"
        instance._calc_response_usage.assert_called_once_with(
            "openai.gpt-5.5", {"aws_region": "us-east-2"}, 10, 5
        )

    def test_non_streaming_response_handles_missing_usage(self) -> None:
        instance = _make_instance()
        instance._calc_response_usage = MagicMock(return_value=_empty_usage())

        response = MagicMock(name="openai_response")
        response.output_text = "Hi"
        response.usage = None

        instance._handle_responses_api_response(
            model="openai.gpt-5.5",
            credentials={},
            response=response,
            prompt_messages=[],
        )

        instance._calc_response_usage.assert_called_once_with("openai.gpt-5.5", {}, 0, 0)

    def test_non_streaming_response_handles_empty_text(self) -> None:
        instance = _make_instance()
        instance._calc_response_usage = MagicMock(return_value=_empty_usage())

        response = MagicMock(name="openai_response")
        response.output_text = None
        response.usage = None

        result = instance._handle_responses_api_response(
            model="openai.gpt-5.5",
            credentials={},
            response=response,
            prompt_messages=[],
        )

        assert result.message.content == ""


class TestHandleResponsesApiStream:
    """The streaming handler dispatches on ``type(event).__name__``,
    so the stub event classes are named exactly what the production
    code checks for.
    """

    def test_streaming_yields_chunk_per_text_delta(self) -> None:
        instance = _make_instance()
        instance._calc_response_usage = MagicMock(return_value=_empty_usage())

        delta1 = ResponseTextDeltaEvent("Hello, ")
        delta2 = ResponseTextDeltaEvent("world!")
        completed = ResponseCompletedEvent(
            response=_FakeResponseWithUsage(input_tokens=10, output_tokens=5)
        )

        chunks = list(
            instance._handle_responses_api_stream(
                model="openai.gpt-5.5",
                credentials={},
                stream_response=iter([delta1, delta2, completed]),
                prompt_messages=[],
            )
        )

        # Two text deltas produce two LLMResultChunk with delta.message.content.
        assert chunks[0].delta.message.content == "Hello, "
        assert chunks[1].delta.message.content == "world!"
        # The final completion chunk carries the usage and finish_reason.
        final = chunks[2]
        assert final.delta.finish_reason == "stop"
        instance._calc_response_usage.assert_called_once_with("openai.gpt-5.5", {}, 10, 5)

    def test_streaming_skips_empty_delta(self) -> None:
        instance = _make_instance()
        instance._calc_response_usage = MagicMock(return_value=_empty_usage())

        empty_delta = ResponseTextDeltaEvent("")
        completed = ResponseCompletedEvent(response=_FakeResponseWithUsage(None, None))

        chunks = list(
            instance._handle_responses_api_stream(
                model="openai.gpt-5.5",
                credentials={},
                stream_response=iter([empty_delta, completed]),
                prompt_messages=[],
            )
        )

        # Empty delta must not produce a chunk; only the completion chunk.
        assert len(chunks) == 1
        assert chunks[0].delta.finish_reason == "stop"

    def test_streaming_unknown_event_type_is_ignored(self) -> None:
        instance = _make_instance()
        instance._calc_response_usage = MagicMock(return_value=_empty_usage())

        other_event = ResponseCreatedEvent()

        chunks = list(
            instance._handle_responses_api_stream(
                model="openai.gpt-5.5",
                credentials={},
                stream_response=iter([other_event]),
                prompt_messages=[],
            )
        )

        # Unrecognised event types are silently skipped.
        assert chunks == []


# ---------------------------------------------------------------------------
# Stub classes for streaming events
# ---------------------------------------------------------------------------
# The streaming handler dispatches on ``type(event).__name__``, so the
# classes below are named exactly what the production code checks for.


class ResponseTextDeltaEvent:
    def __init__(self, delta: str) -> None:
        self.delta = delta


class ResponseCompletedEvent:
    def __init__(self, response) -> None:
        self.response = response


class ResponseCreatedEvent:
    pass


class _FakeResponseWithUsage:
    def __init__(self, input_tokens, output_tokens) -> None:
        self.usage = (
            _FakeUsage(input_tokens, output_tokens)
            if input_tokens is not None and output_tokens is not None
            else None
        )


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
