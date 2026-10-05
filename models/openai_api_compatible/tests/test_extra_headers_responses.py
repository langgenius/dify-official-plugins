"""Regression tests for ``extra_headers`` on the OpenAI Responses API path.

PR #4010 added the ``extra_headers`` model parameter for the Chat
Completions path of the OpenAI-API-compatible provider, but the merge
logic was placed AFTER the early-return dispatch to the Responses API
path (``api_type == "responses"``). That meant ``extra_headers`` only
flowed through the Chat Completions path; users who selected the
Responses API got a silent drop.

This fix moves the merge to the top of ``OpenAILargeLanguageModel
._invoke`` so both dispatch paths see the merged credentials. The
``_chat_generate_with_responses`` path threads ``credentials`` into
``_create_openai_client(credentials)``, which passes ``default_headers``
to the OpenAI SDK client; the merged ``extra_headers`` therefore ride
on every ``client.responses.create(...)`` call.

See https://github.com/langgenius/dify-official-plugins/pull/4010
(issue #3865) for the original feature request and PR #4010 for the
Chat Completions side. The test file mirrors the structure of
``test_extra_headers.py`` but exercises the Responses API dispatch.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import OpenAILargeLanguageModel

# Patch the Responses API method on the plugin class. The base
# `_create_openai_client` builds an `OpenAI(...)` client that issues a
# real network request; we replace `_chat_generate_with_responses` so
# the test runs offline.
CHAT_GENERATE_WITH_RESPONSES = (
    "models.llm.llm.OpenAILargeLanguageModel._chat_generate_with_responses"
)


def _user_message():
    return UserPromptMessage(content="ping")


def _capture_invoke_responses(credentials, model_parameters, model="gpt-5-mini"):
    """Run ``_invoke`` with ``api_type == 'responses'`` and return the captured credentials."""
    credentials = dict(credentials)
    credentials["api_type"] = "responses"
    llm = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_responses(
        self,
        model,
        credentials,
        prompt_messages,
        model_parameters,
        tools,
        stop,
        stream,
        user,
    ):
        captured["credentials"] = credentials
        captured["model_parameters"] = dict(model_parameters)
        # Return a stand-in result. The caller does not post-process
        # this on the responses path (no thinking filter).
        return MagicMock()

    with patch(CHAT_GENERATE_WITH_RESPONSES, new=fake_responses):
        llm._invoke(
            model=model,
            credentials=credentials,
            prompt_messages=_user_message(),
            model_parameters=dict(model_parameters),
            stream=False,
        )

    return captured


# ---------------------------------------------------------------------------
# Disabled / no-op paths
# ---------------------------------------------------------------------------


def test_no_extra_headers_param_leaves_credentials_untouched():
    """Without the parameter, credentials flow through unchanged on the Responses path."""
    captured = _capture_invoke_responses(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
        },
        model_parameters={"max_tokens": 128},
    )
    assert "extra_headers" not in captured["credentials"]


def test_empty_extra_headers_value_does_not_break_invocation():
    """Empty-string value: parse error → no-op, original credentials preserved."""
    captured = _capture_invoke_responses(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
        },
        model_parameters={"extra_headers": ""},
    )
    assert "extra_headers" not in captured["credentials"]


def test_invalid_json_extra_headers_does_not_break_invocation():
    """Non-JSON garbage: parse error → no-op (never raises)."""
    captured = _capture_invoke_responses(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
        },
        model_parameters={"extra_headers": "not-a-json-object"},
    )
    assert "extra_headers" not in captured["credentials"]


def test_extra_headers_is_popped_from_model_parameters():
    """The ``extra_headers`` key is consumed on the Responses path too."""
    captured = _capture_invoke_responses(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
        },
        model_parameters={"extra_headers": '{"x-trace-id": "abc"}'},
    )
    assert "extra_headers" not in captured["model_parameters"]


# ---------------------------------------------------------------------------
# Positive paths — the actual bug fix
# ---------------------------------------------------------------------------


def test_responses_api_path_receives_merged_extra_headers():
    """The pre-fix bug: extra_headers were dropped on the Responses API path.

    With the fix, the merge runs at the top of ``_invoke`` (BEFORE the
    dispatch to ``_chat_generate_with_responses``), so the captured
    credentials include the merged entry. ``_create_openai_client``
    passes this directly to ``default_headers=`` on the OpenAI SDK
    client, and every ``client.responses.create(...)`` call rides on it.
    """
    captured = _capture_invoke_responses(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
        },
        model_parameters={"extra_headers": '{"x-opencode-session": "abc-123"}'},
    )
    assert captured["credentials"]["extra_headers"] == {"x-opencode-session": "abc-123"}


def test_responses_api_path_merges_on_top_of_credential_extra_headers():
    """Per-model extra_headers merge on top of existing ``credential['extra_headers']``."""
    captured = _capture_invoke_responses(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
            "extra_headers": {"x-tenant-id": "tenant-1"},
        },
        model_parameters={"extra_headers": '{"x-opencode-session": "dyn-id"}'},
    )
    assert captured["credentials"]["extra_headers"] == {
        "x-tenant-id": "tenant-1",
        "x-opencode-session": "dyn-id",
    }


def test_responses_api_path_dict_passes_through():
    """A dict value (not a string) is accepted as-is and forwarded."""
    captured = _capture_invoke_responses(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
        },
        model_parameters={"extra_headers": {"x-trace-id": "abc", "x-tenant-id": "tenant-1"}},
    )
    assert captured["credentials"]["extra_headers"] == {
        "x-trace-id": "abc",
        "x-tenant-id": "tenant-1",
    }


def test_responses_api_path_does_not_mutate_input_credentials():
    """The plugin does not mutate the caller's ``credentials`` dict in place."""
    credentials = {
        "mode": "chat",
        "endpoint_url": "https://api.example.com/v1",
        "api_type": "responses",
    }
    captured = _capture_invoke_responses(
        credentials=credentials,
        model_parameters={"extra_headers": '{"x-trace-id": "abc"}'},
    )
    assert "extra_headers" not in credentials  # original untouched
    assert captured["credentials"]["extra_headers"] == {"x-trace-id": "abc"}