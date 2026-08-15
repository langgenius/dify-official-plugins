"""Regression test for the bare ``except Exception`` wrapper in
``_invoke``'s inference-profile branch (issue #3653).

Pre-fix, ``_invoke`` wrapped the entire inference-profile branch in
``except Exception as e: raise InvokeError(f"Failed to invoke inference
profile {id}: {e}")``. A ``NameError`` / ``TypeError`` / ``KeyError`` /
or any other non-``InvokeError`` exception raised inside the block
surfaced to the caller as a generic ``InvokeError`` whose message
contained the original exception string. The root-cause type and
traceback were lost.

The fix mirrors PR #3565 (issue #3564), which addressed the same
anti-pattern in ``_generate``:
- ``except InvokeError: raise`` lets legitimate errors propagate unchanged.
- ``except Exception: logger.exception(...); raise`` logs the full
  traceback at ERROR level and re-raises the original exception so the
  caller sees its real type.

These tests pin:
1. A non-``InvokeError`` exception (e.g. ``NameError``) propagates
   unchanged — not wrapped in ``InvokeError``.
2. The existing ``InvokeError("Could not get model information...")``
   raise inside the try block still propagates as ``InvokeError``.
3. A source-level guard: the inference-profile branch in ``llm.py``
   does not contain ``raise InvokeError(f"Failed to invoke inference
   profile {str(e)}")`` — the old wrapper that swallowed exceptions.
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock

import pytest

from dify_plugin.errors.model import InvokeError

llm_mod = importlib.import_module("models.llm.llm")
BedrockLLM = llm_mod.BedrockLargeLanguageModel


def _make_instance() -> BedrockLLM:
    """Construct a ``BedrockLargeLanguageModel`` without invoking the real
    plugin-runtime ``__init__``. Method-level tests mock the methods
    they exercise.
    """
    return object.__new__(BedrockLLM)


_INFERENCE_PROFILE_CREDENTIALS = {
    "aws_region": "us-east-1",
    "inference_profile_id": "arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123",
}


class TestInferenceProfilePropagatesNonInvokeError:
    """Pre-fix, any non-``InvokeError`` exception inside the
    inference-profile branch was wrapped in ``InvokeError``. The fix
    lets the original exception propagate so the caller sees the
    real type (and the full traceback, captured by ``logger.exception``).
    """

    def test_name_error_propagates_unchanged(self) -> None:
        instance = _make_instance()
        instance._get_model_info = MagicMock(side_effect=NameError("simulated bug"))
        with pytest.raises(NameError, match="simulated bug"):
            instance._invoke(
                model="anthropic.claude-5-opus",
                credentials=_INFERENCE_PROFILE_CREDENTIALS,
                prompt_messages=[],
                model_parameters={},
                stop=None,
                stream=True,
                user=None,
            )

    def test_type_error_propagates_unchanged(self) -> None:
        instance = _make_instance()
        instance._get_model_info = MagicMock(side_effect=TypeError("bad arg"))
        with pytest.raises(TypeError, match="bad arg"):
            instance._invoke(
                model="anthropic.claude-5-opus",
                credentials=_INFERENCE_PROFILE_CREDENTIALS,
                prompt_messages=[],
                model_parameters={},
                stop=None,
                stream=True,
                user=None,
            )

    def test_key_error_propagates_unchanged(self) -> None:
        instance = _make_instance()
        instance._get_model_info = MagicMock(side_effect=KeyError("missing-key"))
        with pytest.raises(KeyError):
            instance._invoke(
                model="anthropic.claude-5-opus",
                credentials=_INFERENCE_PROFILE_CREDENTIALS,
                prompt_messages=[],
                model_parameters={},
                stop=None,
                stream=True,
                user=None,
            )

    def test_attribute_error_propagates_unchanged(self) -> None:
        """Real bug seen in production: a downstream method returns
        ``None`` and the next line accesses ``.get(...)`` on it.
        Pre-fix, this would have surfaced as ``InvokeError("Failed to
        invoke inference profile ...: 'NoneType' object has no
        attribute 'get'")`` — misleading.
        """
        instance = _make_instance()
        instance._get_model_info = MagicMock(
            side_effect=AttributeError("'NoneType' object has no attribute 'get'")
        )
        with pytest.raises(AttributeError, match="NoneType"):
            instance._invoke(
                model="anthropic.claude-5-opus",
                credentials=_INFERENCE_PROFILE_CREDENTIALS,
                prompt_messages=[],
                model_parameters={},
                stop=None,
                stream=True,
                user=None,
            )


class TestInferenceProfileInvokeErrorStillPropagates:
    """The legitimate ``InvokeError("Could not get model information
    for inference profile ...")`` raise inside the try block must
    still propagate as ``InvokeError``. The fix must not swallow the
    intended error path.
    """

    def test_known_invoke_error_propagates_unchanged(self) -> None:
        instance = _make_instance()
        instance._get_model_info = MagicMock(return_value=None)
        with pytest.raises(InvokeError, match="Could not get model information"):
            instance._invoke(
                model="anthropic.claude-5-opus",
                credentials=_INFERENCE_PROFILE_CREDENTIALS,
                prompt_messages=[],
                model_parameters={},
                stop=None,
                stream=True,
                user=None,
            )


class TestInferenceProfileErrorIsLogged:
    """When a non-``InvokeError`` exception occurs, the fix uses
    ``logger.exception`` so the full traceback is captured at ERROR
    level. The previous code used ``logger.error(str(e))`` which lost
    the traceback.
    """

    def test_non_invoke_error_logs_with_traceback(self, caplog) -> None:
        instance = _make_instance()
        instance._get_model_info = MagicMock(side_effect=NameError("logged bug"))
        with caplog.at_level(logging.ERROR, logger="models.llm.llm"):
            with pytest.raises(NameError):
                instance._invoke(
                    model="anthropic.claude-5-opus",
                    credentials=_INFERENCE_PROFILE_CREDENTIALS,
                    prompt_messages=[],
                    model_parameters={},
                    stop=None,
                    stream=True,
                    user=None,
                )
        assert any(
            "inference profile" in record.message.lower() for record in caplog.records
        ), "logger.exception should fire for non-InvokeError exceptions"


class TestNoInvokeErrorWrapperInSource:
    """Belt-and-braces: the source must not contain the old wrapper
    pattern that re-raised as ``InvokeError(f"Failed to invoke
    inference profile {str(e)}")``. A future refactor that re-adds
    the wrapper would silently re-introduce the bug.
    """

    def test_no_old_wrapper_in_inference_profile_block(self) -> None:
        from pathlib import Path

        source_path = Path(llm_mod.__file__).resolve()
        with open(source_path, encoding="utf-8") as fh:
            source = fh.read()
        assert 'raise InvokeError(f"Failed to invoke inference profile' not in source, (
            f"Old `raise InvokeError(f'Failed to invoke inference profile {{str(e)}}')` "
            f"wrapper has reappeared in {source_path}; this was the bug fixed in "
            f"PR fixing issue #3653."
        )
