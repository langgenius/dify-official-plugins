"""Regression test for the bare ``except Exception`` wrapper in
``_generate_with_converse`` (issue #3660).

Pre-fix, ``_generate_with_converse`` ended with ``except Exception as ex:
raise InvokeError(str(ex))``. A ``NameError`` / ``TypeError`` / ``KeyError``
or any other non-``InvokeError`` exception raised inside the converse API
path surfaced to the caller as a generic ``InvokeError`` whose message
contained the original exception string, hiding the root cause and
traceback.

The fix mirrors PR #3565 (issue #3564) and PR #3654 (issue #3653), which
addressed the same anti-pattern in ``_generate`` and ``_invoke``:
- ``except InvokeError: raise`` lets legitimate errors propagate unchanged.
- ``except Exception: logger.exception(...); raise`` logs the full
  traceback at ERROR level and re-raises the original exception so the
  caller sees its real type.

These tests pin:
1. A non-``InvokeError`` exception (e.g. ``NameError``) raised inside
   the try block (by the bedrock client itself) propagates unchanged —
   not wrapped in ``InvokeError``.
2. The existing ``ClientError`` handler still maps to the right
   ``InvokeError`` subclasses.
3. The existing ``EndpointConnectionError`` and ``UnknownServiceError``
   handlers still map to the right ``InvokeError`` subclasses.
4. A source-level guard: the old wrapper cannot re-appear in a future
   refactor.
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, UnknownServiceError

from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

llm_mod = importlib.import_module("models.llm.llm")
BedrockLLM = llm_mod.BedrockLargeLanguageModel


def _make_instance() -> BedrockLLM:
    """Construct a ``BedrockLargeLanguageModel`` without invoking the real
    plugin-runtime ``__init__``. Method-level tests mock the methods
    they exercise.
    """
    return object.__new__(BedrockLLM)


def _client_error(code: str, message: str = "msg") -> ClientError:
    """Construct a ``botocore.exceptions.ClientError`` with the given
    error code and message.
    """
    return ClientError({"Error": {"Code": code, "Message": message}}, "converse")


_BASE_MODEL_INFO = {
    "model": "anthropic.claude-5-opus",
    "support_system_prompts": True,
    "support_tool_use": True,
}


def _build_response_handler_instance() -> tuple[BedrockLLM, MagicMock]:
    """Build an instance with a mocked bedrock client whose ``converse``
    call raises the exception supplied by the caller. The ``_generate_with_converse``
    method falls through to the trailing ``except Exception`` block when
    the exception is not a known boto3 type.
    """
    instance = _make_instance()
    return instance, MagicMock(name="bedrock_client")


class TestConversePropagatesNonInvokeError:
    """Pre-fix, any non-``InvokeError`` exception inside
    ``_generate_with_converse`` was wrapped in ``InvokeError``. The fix
    lets the original exception propagate so the caller sees the
    real type (and the full traceback, captured by ``logger.exception``).

    The trigger is a bedrock_client.converse() that raises a non-boto3
    exception (e.g. NameError) — none of the specific ``except`` blocks
    catch it, so it falls through to the trailing ``except Exception``
    block.
    """

    def test_name_error_propagates_unchanged(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = NameError("simulated bug")
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(NameError, match="simulated bug"):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )

    def test_type_error_propagates_unchanged(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = TypeError("bad arg")
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(TypeError, match="bad arg"):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )

    def test_key_error_propagates_unchanged(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = KeyError("missing-key")
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(KeyError):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )

    def test_attribute_error_propagates_unchanged(self) -> None:
        """Real bug seen in production: a downstream method returns
        ``None`` and the next line accesses ``.get(...)`` on it.
        Pre-fix, this would have surfaced as ``InvokeError("'NoneType'
        object has no attribute 'get'")`` — misleading.
        """
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = AttributeError(
            "'NoneType' object has no attribute 'get'"
        )
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(AttributeError, match="NoneType"):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )


class TestConverseClientErrorStillMapped:
    """The legitimate ``ClientError`` handler in
    ``_generate_with_converse`` (ThrottlingException, AccessDeniedException,
    ValidationException, etc.) must still map to the right ``InvokeError``
    subclasses. The fix must not break the intended error path.
    """

    def test_throttling_maps_to_invoke_rate_limit(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = _client_error("ThrottlingException", "rate")
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(InvokeRateLimitError):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )

    def test_access_denied_maps_to_invoke_authorization(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = _client_error("AccessDeniedException", "denied")
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(InvokeAuthorizationError):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )

    def test_validation_maps_to_invoke_bad_request(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = _client_error("ValidationException", "bad input")
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(InvokeBadRequestError):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )


class TestConverseConnectionAndServiceErrors:
    """The ``EndpointConnectionError`` and ``UnknownServiceError`` handlers
    must still map to the right ``InvokeError`` subclasses.
    """

    def test_endpoint_connection_error_maps_to_invoke_connection_error(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = EndpointConnectionError(
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(InvokeConnectionError):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )

    def test_unknown_service_error_maps_to_invoke_server_unavailable(self) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = UnknownServiceError(
            known_service_names="bedrock", service_name="bedrock", region_name="us-east-1"
        )
        with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
            with pytest.raises(InvokeServerUnavailableError):
                instance._generate_with_converse(
                    model_info=_BASE_MODEL_INFO,
                    credentials={"aws_region": "us-east-1"},
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=False,
                    user=None,
                )


class TestConverseErrorIsLogged:
    """When a non-``InvokeError`` exception occurs, the fix uses
    ``logger.exception`` so the full traceback is captured at ERROR
    level. The previous code used ``logger.error(str(e))`` which lost
    the traceback.
    """

    def test_non_invoke_error_logs_with_traceback(self, caplog) -> None:
        instance, bedrock_client = _build_response_handler_instance()
        bedrock_client.converse.side_effect = NameError("logged bug")
        with caplog.at_level(logging.ERROR, logger="models.llm.llm"):
            with patch.object(llm_mod, "get_bedrock_client", return_value=bedrock_client):
                with pytest.raises(NameError):
                    instance._generate_with_converse(
                        model_info=_BASE_MODEL_INFO,
                        credentials={"aws_region": "us-east-1"},
                        prompt_messages=[],
                        model_parameters={},
                        stop=None,
                        stream=False,
                        user=None,
                    )
        assert any(
            "converse model" in record.message.lower() for record in caplog.records
        ), "logger.exception should fire for non-InvokeError exceptions"
