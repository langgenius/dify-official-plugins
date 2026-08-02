"""Regression test for the undefined ``runtime_client`` bug in the legacy
``_generate`` method (issue #3564).

The pre-fix code in ``models/bedrock/models/llm/llm.py`` created a
``bedrock_client`` via ``get_bedrock_client("bedrock-runtime", credentials)``
and then referenced an undefined ``runtime_client`` on the next two lines::

    bedrock_client = get_bedrock_client("bedrock-runtime", credentials)
    ...
    if stream and model_prefix != "ai21":
        invoke = runtime_client.invoke_model_with_response_stream  # NameError
    else:
        invoke = runtime_client.invoke_model                       # NameError

The first invocation that reached this code path raised ``NameError: name
'runtime_client' is not defined``, which the bare ``except Exception`` block
swallowed and re-raised as ``InvokeError(str(ex))`` — surfacing the
stringified ``NameError`` to the caller instead of the actual cause.

The fix substitutes ``bedrock_client`` for ``runtime_client`` in both call
sites. This test pins the fix: the streaming path must call
``bedrock_client.invoke_model_with_response_stream``; the non-streaming
path must call ``bedrock_client.invoke_model``; neither path may raise
``NameError``.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

llm_mod = importlib.import_module("models.llm.llm")

BedrockLLM = llm_mod.BedrockLargeLanguageModel


def _make_instance():
    """Construct a BedrockLargeLanguageModel without going through the
    plugin runtime's ``__init__`` (which would require a full provider
    config). Object.__new__ bypasses the real ``__init__`` and lets us
    drive the method under test directly with mocks for the boto3
    client, the payload builder, and the response handlers.
    """
    instance = object.__new__(BedrockLLM)
    instance._create_payload = MagicMock(return_value={"messages": []})
    instance._handle_generate_stream_response = MagicMock(return_value="STREAMED")
    instance._handle_generate_response = MagicMock(return_value="NON_STREAMED")
    return instance


class TestLegacyGenerateUsesBedrockClient:
    """The legacy ``_generate`` fallback (reached for models whose ID
    prefix is not in ``CONVERSE_API_ENABLED_MODEL_INFO``) must use the
    client returned by ``get_bedrock_client``. Before the fix it
    referenced an undefined ``runtime_client`` and raised ``NameError``.
    """

    def test_streaming_path_calls_bedrock_client_invoke_model_with_response_stream(
        self,
    ) -> None:
        instance = _make_instance()
        mock_client = MagicMock(name="bedrock_client")
        mock_client.invoke_model_with_response_stream.return_value = "raw_stream"

        with (
            patch.object(llm_mod, "get_bedrock_client", return_value=mock_client),
        ):
            result = instance._generate(
                model="cohere.command-text-v14",
                credentials={"aws_region": "us-east-1"},
                prompt_messages=[],
                model_parameters={"max_tokens": 64},
                stop=None,
                stream=True,
                user=None,
            )

        # bedrock_client is used; runtime_client is not referenced at all.
        mock_client.invoke_model_with_response_stream.assert_called_once()
        mock_client.invoke_model.assert_not_called()
        # The streaming response handler consumes the raw stream.
        instance._handle_generate_stream_response.assert_called_once()
        instance._handle_generate_response.assert_not_called()
        assert result == "STREAMED"

    def test_non_streaming_path_calls_bedrock_client_invoke_model(
        self,
    ) -> None:
        instance = _make_instance()
        mock_client = MagicMock(name="bedrock_client")
        mock_client.invoke_model.return_value = "raw_response"

        with patch.object(llm_mod, "get_bedrock_client", return_value=mock_client):
            result = instance._generate(
                model="cohere.command-text-v14",
                credentials={"aws_region": "us-east-1"},
                prompt_messages=[],
                model_parameters={"max_tokens": 64},
                stop=None,
                stream=False,
                user=None,
            )

        mock_client.invoke_model.assert_called_once()
        mock_client.invoke_model_with_response_stream.assert_not_called()
        instance._handle_generate_response.assert_called_once()
        instance._handle_generate_stream_response.assert_not_called()
        assert result == "NON_STREAMED"

    def test_ai21_non_streaming_uses_invoke_model(self) -> None:
        """The pre-fix comment says "ai21 models don't support streaming",
        so the non-streaming branch must use ``invoke_model`` even when
        ``stream=True`` for an ``ai21.*`` model.
        """
        instance = _make_instance()
        mock_client = MagicMock(name="bedrock_client")
        mock_client.invoke_model.return_value = "raw_response"

        with patch.object(llm_mod, "get_bedrock_client", return_value=mock_client):
            instance._generate(
                model="ai21.jamba-1-0-large",
                credentials={"aws_region": "us-east-1"},
                prompt_messages=[],
                model_parameters={"max_tokens": 64},
                stop=None,
                stream=True,  # ignored for ai21
                user=None,
            )

        # ai21 must fall through to invoke_model, not invoke_model_with_response_stream.
        mock_client.invoke_model.assert_called_once()
        mock_client.invoke_model_with_response_stream.assert_not_called()

    def test_legacy_generate_does_not_raise_name_error(self) -> None:
        """Directly assert the pre-fix NameError is gone. Before the fix
        this raised ``NameError: name 'runtime_client' is not defined``
        on the first call to ``invoke``.
        """
        instance = _make_instance()
        mock_client = MagicMock(name="bedrock_client")
        mock_client.invoke_model_with_response_stream.return_value = "raw_stream"

        with patch.object(llm_mod, "get_bedrock_client", return_value=mock_client):
            # Must not raise.
            instance._generate(
                model="cohere.command-text-v14",
                credentials={"aws_region": "us-east-1"},
                prompt_messages=[],
                model_parameters={"max_tokens": 64},
                stop=None,
                stream=True,
                user=None,
            )

    def test_no_runtime_client_references_in_module(self) -> None:
        """Belt-and-braces: the source must not reference ``runtime_client``
        anywhere. Catches a future refactor that re-introduces the bug.
        """
        from pathlib import Path

        source_path = Path(llm_mod.__file__).resolve()
        with open(source_path, encoding="utf-8") as fh:
            source = fh.read()
        assert "runtime_client" not in source, (
            f"runtime_client has reappeared in {source_path}; "
            "this was the undefined-name bug fixed in PR #3565 (issue #3564)."
        )
