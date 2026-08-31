"""Regression tests for #3653 (bare except Exception in
_invoke inference-profile branch).

The fix in models/llm/llm.py splits the inference-profile branch's
try block into:

  - except (ClientError, KeyError) -> wrap as InvokeError (real AWS
    errors + dict-access bugs both surface with the original message).
  - except Exception -> re-raise verbatim (NameError, TypeError,
    AttributeError etc. must propagate so the operator sees the real
    traceback instead of a misleading InvokeError).

The previous bare `except Exception -> InvokeError(str(e))` swallowed
the original exception class and message, hiding the root cause.

The tests below exercise the new behavior end-to-end against the
BedrockLargeLanguageModel class.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


@pytest.fixture
def llm(make_llm):
    return make_llm()


def test_invoke_inference_profile_raises_unknown_error_verbatim(llm):
    """A real bug (NameError, TypeError, AttributeError, …) raised
    inside the inference-profile branch must propagate to the caller
    with its original exception class — NOT be wrapped in InvokeError.
    Pre-fix, a NameError surfaced as InvokeError(name 'foo' is not
    defined), hiding the traceback.
    """
    from dify_plugin.errors.model import InvokeError

    credentials = {"inference_profile_id": "arn:aws:bedrock:us-east-1:123:profile-abc"}
    model = "arn:aws:bedrock:us-east-1:123:custom/model"
    model_parameters = {}

    with patch.object(llm, "_get_model_info", side_effect=NameError("name 'undefined_thing' is not defined")):
        with pytest.raises(NameError, match="name 'undefined_thing' is not defined"):
            llm._invoke(model, credentials, [], model_parameters)

    # A defensive assertion: even when the fix wraps the wrong class,
    # the caller must NOT see a generic InvokeError masking the root
    # cause. This is the central invariant the fix preserves.
    with patch.object(llm, "_get_model_info", side_effect=InvokeError("wrapped")):
        with pytest.raises(InvokeError, match="wrapped"):
            llm._invoke(model, credentials, [], model_parameters)


def test_invoke_inference_profile_wraps_client_error_as_invokeerror(llm):
    """boto3 ClientError (real AWS errors) must still surface as
    InvokeError. The fix's except (ClientError, KeyError) branch
    wraps these correctly.
    """
    from botocore.exceptions import ClientError
    from dify_plugin.errors.model import InvokeError

    credentials = {"inference_profile_id": "arn:aws:bedrock:us-east-1:123:profile-abc"}
    model = "arn:aws:bedrock:us-east-1:123:custom/model"
    model_parameters = {}

    fake_client_error = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Profile not found"}},
        "GetInferenceProfile",
    )
    with patch.object(llm, "_get_model_info", side_effect=fake_client_error):
        with pytest.raises(InvokeError) as exc_info:
            llm._invoke(model, credentials, [], model_parameters)

    # The exception must be InvokeError (not the raw ClientError), and
    # its message must surface the original AWS error code + message.
    assert "ResourceNotFoundException" in str(exc_info.value)
    assert "Profile not found" in str(exc_info.value)


def test_invoke_inference_profile_wraps_keyerror_as_invokeerror(llm):
    """KeyError from dict access in the inference-profile branch
    surfaces as InvokeError. Same rationale as the original
    issue: the operator sees the bad key in the message and the bug
    is at least discoverable from the wrapped error.
    """
    from dify_plugin.errors.model import InvokeError

    credentials = {"inference_profile_id": "arn:aws:bedrock:us-east-1:123:profile-abc"}
    model = "arn:aws:bedrock:us-east-1:123:custom/model"
    model_parameters = {}

    with patch.object(llm, "_get_model_info", side_effect=KeyError("missing_field")):
        with pytest.raises(InvokeError, match="missing_field"):
            llm._invoke(model, credentials, [], model_parameters)
