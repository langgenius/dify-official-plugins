"""Regression tests for the ``extra_headers`` model parameter in OpenAILargeLanguageModel.

The OpenAI-API-compatible provider previously hardcoded its outbound
HTTP headers to a small set (Content-Type, Accept-Charset, plus any
``credentials['extra_headers']`` set on the provider credential) and
there was no way for users to add per-invocation HTTP headers. Newer
Dify versions support resolving workflow/system variables in string-type
model parameters, which makes per-model custom headers useful for:

- session affinity (e.g. ``x-opencode-session`` for OpenCode Go, which
  now requires a stable per-conversation session ID and returns
  HTTP 400 ``MissingSessionID`` when missing)
- distributed tracing
- tenant identification
- vendor-specific OpenAI-compatible extensions

The fix adds an ``extra_headers`` model parameter that accepts a JSON
object string. The plugin parses it at request time and merges the
entries into ``credentials['extra_headers']`` for that single request;
the OAICompat base class then threads the merged headers into the
outbound ``requests.post`` call.

See https://github.com/langgenius/dify-official-plugins/issues/3865.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import OpenAILargeLanguageModel

SUPER_INVOKE = (
    "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke"
)


def _user_message():
    return UserPromptMessage(content="ping")


def _capture_invoke(credentials, model_parameters, model="gpt-4o-mini"):
    """Run ``_invoke`` with the base implementation stubbed out and return ``credentials``."""
    llm = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = credentials
        captured["model_parameters"] = dict(model_parameters)
        # Non-streaming: return a stand-in that the caller can introspect
        # for the thinking-filter post-processing path (which checks
        # ``result.message``).
        return MagicMock()

    with patch(SUPER_INVOKE, new=fake_super):
        llm._invoke(
            model=model,
            credentials=dict(credentials),
            prompt_messages=_user_message(),
            model_parameters=dict(model_parameters),
            stream=False,
        )

    return captured


# ---------------------------------------------------------------------------
# Disabled / no-op paths
# ---------------------------------------------------------------------------


def test_no_extra_headers_param_leaves_credentials_untouched():
    """Without the parameter, credentials flow through unchanged."""
    captured = _capture_invoke(
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
        model_parameters={"max_tokens": 128},
    )
    assert "extra_headers" not in captured["credentials"]


def test_empty_extra_headers_value_does_not_break_invocation():
    """Empty-string value: parse error → no-op, original credentials preserved."""
    captured = _capture_invoke(
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
        model_parameters={"extra_headers": ""},
    )
    assert "extra_headers" not in captured["credentials"]


def test_invalid_json_extra_headers_does_not_break_invocation():
    """Non-JSON garbage: parse error → no-op (never raises)."""
    captured = _capture_invoke(
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
        model_parameters={"extra_headers": "not-a-json-object"},
    )
    assert "extra_headers" not in captured["credentials"]


def test_extra_headers_is_popped_from_model_parameters():
    """The ``extra_headers`` key is consumed; it does not flow into the request body."""
    captured = _capture_invoke(
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
        model_parameters={"extra_headers": '{"x-trace-id": "abc"}'},
    )
    assert "extra_headers" not in captured["model_parameters"]


# ---------------------------------------------------------------------------
# Positive paths
# ---------------------------------------------------------------------------


def test_extra_headers_string_object_merged_into_credentials():
    """JSON object string is parsed and forwarded via credentials."""
    captured = _capture_invoke(
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
        model_parameters={"extra_headers": '{"x-opencode-session": "abc-123"}'},
    )
    assert captured["credentials"]["extra_headers"] == {"x-opencode-session": "abc-123"}


def test_extra_headers_dict_passes_through():
    """A dict value (not a string) is accepted as-is and forwarded."""
    captured = _capture_invoke(
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
        model_parameters={"extra_headers": {"x-trace-id": "abc", "x-tenant-id": "tenant-1"}},
    )
    assert captured["credentials"]["extra_headers"] == {
        "x-trace-id": "abc",
        "x-tenant-id": "tenant-1",
    }


def test_extra_headers_merge_on_top_of_credential_extra_headers():
    """Per-model extra_headers are merged on top of existing ``credential['extra_headers']``."""
    captured = _capture_invoke(
        credentials={
            "mode": "chat",
            "endpoint_url": "https://api.example.com/v1",
            "extra_headers": {"x-tenant-id": "tenant-1", "x-opencode-session": "static-id"},
        },
        model_parameters={"extra_headers": '{"x-opencode-session": "dyn-id"}'},
    )
    assert captured["credentials"]["extra_headers"] == {
        "x-tenant-id": "tenant-1",
        "x-opencode-session": "dyn-id",  # per-model wins on collision
    }


def test_extra_headers_does_not_mutate_input_credentials():
    """The plugin does not mutate the caller's ``credentials`` dict in place."""
    credentials = {"mode": "chat", "endpoint_url": "https://api.example.com/v1"}
    captured = _capture_invoke(
        credentials=credentials,
        model_parameters={"extra_headers": '{"x-trace-id": "abc"}'},
    )
    assert "extra_headers" not in credentials  # original untouched
    assert captured["credentials"]["extra_headers"] == {"x-trace-id": "abc"}


def test_extra_headers_with_dify_template_already_resolved():
    """A pre-resolved template value (Dify core resolves upstream) is forwarded verbatim."""
    # Dify resolves `{{#sys.conversation_id#}}` to the actual ID before
    # the plugin sees it. The plugin only sees the resolved string.
    captured = _capture_invoke(
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
        model_parameters={"extra_headers": '{"x-opencode-session": "abc-123-resolved"}'},
    )
    assert captured["credentials"]["extra_headers"]["x-opencode-session"] == "abc-123-resolved"


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------


def test_extra_headers_param_rule_is_exposed():
    """``extra_headers`` must appear in the model parameter rules."""
    llm = OpenAILargeLanguageModel(model_schemas=[])
    entity = llm.get_customizable_model_schema(
        model="custom-model",
        credentials={"mode": "chat", "endpoint_url": "https://api.example.com/v1"},
    )
    names = {rule.name for rule in entity.parameter_rules}
    assert "extra_headers" in names, (
        "extra_headers must appear in the model parameter rules so it shows "
        "up in the Dify Model Provider UI"
    )