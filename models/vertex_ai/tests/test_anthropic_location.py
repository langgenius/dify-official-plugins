"""Regression tests for tolerating a missing vertex_anthropic_location credential.

Covers GitHub issue #4004: when a user leaves the optional "Anthropic
Models Location" field blank in the Vertex AI provider config, Dify drops
the key from saved credentials. The Anthropic dispatch path previously
read it with credentials["vertex_anthropic_location"], which raised
KeyError before any request was sent. The fix switches the read to
credentials.get(...) so the downstream `if vertex_anthropic_location:`
fallback handles the missing case.

These tests pin:

  * the location-resolution chain tolerates a missing or empty
    vertex_anthropic_location without raising;
  * vertex_location is used as the fallback when no Anthropic-specific
    location is set;
  * the model-name-based default still applies when neither location is
    set;
  * a source-level guard pins the defensive read on llm.py.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

import models.llm.llm as llm_module
from models.llm.llm import VertexAiLargeLanguageModel

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
LLM_PY = PLUGIN_ROOT / "models" / "llm" / "llm.py"

# Model names that should land on the model-name-based default of us-east5
# when neither vertex_anthropic_location nor vertex_location is set.
US_EAST5_MODELS = [
    "claude-opus-4-5@20250929",
    "claude-sonnet-4-5@20250929",
    "claude-sonnet-5",
]

# Older Claude 3 models should land on us-central1 under the same conditions.
US_CENTRAL_MODELS = [
    "claude-3-haiku@20240307",
    "claude-3-sonnet@20240229",
]


class _CapturedClient:
    """Stand-in for AnthropicVertex that records the kwargs it was constructed with."""

    instances: list[dict[str, Any]] = []

    @classmethod
    def reset(cls) -> None:
        cls.instances = []

    def __init__(self, *, region: str, project_id: str, access_token: str | None = None):
        type(self).instances.append(
            {"region": region, "project_id": project_id, "access_token": access_token}
        )

    def __getattr__(self, name: str) -> Any:
        # Anything not on this stub becomes a no-op callable so .messages.create()
        # returns something harmless for the no-credentials default flow.
        def _noop(*_args: Any, **_kwargs: Any) -> Any:
            return None
        return _noop


def _instance() -> VertexAiLargeLanguageModel:
    return VertexAiLargeLanguageModel.__new__(VertexAiLargeLanguageModel)


def _invoke_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    *,
    credentials: dict[str, Any],
    model: str,
    stream: bool = False,
) -> _CapturedClient:
    """Run just the Anthropic dispatch path up to client construction. Mock the SDK
    constructor and the `messages.create` call so the test doesn't actually hit Google.

    Returns the captured AnthropicVertex stub so the test can assert the region.
    """
    _CapturedClient.reset()
    monkeypatch.setattr(llm_module, "AnthropicVertex", _CapturedClient)

    instance = _instance()
    # Invoke through the streaming=True branch because the streaming helper
    # pulls chunks off `response` which we never feed it. But we never get
    # that far without an exception because the constructor call happens
    # before .messages.create. So we can use stream=False and rely on
    # _handle_claude_response failing on the fake response — we'll never reach
    # that path because the test asserts on the captured client instead.
    try:
        instance._generate_anthropic(
            model=model,
            credentials=credentials,
            prompt_messages=[],
            model_parameters={},
            stream=stream,
            user=None,
        )
    except Exception:
        # Anything past client construction is irrelevant; the test asserts
        # on the captured stub. Swallow so the assertion path is clean.
        pass
    assert _CapturedClient.instances, "AnthropicVertex was never constructed"
    return _CapturedClient


# ---------------------------------------------------------------------------
# Resolution chain
# ---------------------------------------------------------------------------

def test_missing_vertex_anthropic_location_falls_back_to_vertex_location(monkeypatch: pytest.MonkeyPatch):
    """Issue #4004 repro: vertex_anthropic_location is absent. Must not raise."""
    captured = _invoke_anthropic(
        monkeypatch,
        model="claude-3-sonnet@20240229",
        credentials={
            "vertex_project_id": "test-project",
            "vertex_location": "europe-west4",
            # Note: vertex_anthropic_location intentionally absent.
        },
    )
    assert captured.instances[0]["region"] == "europe-west4"


def test_empty_vertex_anthropic_location_falls_back_to_vertex_location(monkeypatch: pytest.MonkeyPatch):
    """An empty string is also 'unset' for the coordinator's purpose."""
    captured = _invoke_anthropic(
        monkeypatch,
        model="claude-3-sonnet@20240229",
        credentials={
            "vertex_project_id": "test-project",
            "vertex_location": "europe-west4",
            "vertex_anthropic_location": "",
        },
    )
    assert captured.instances[0]["region"] == "europe-west4"


def test_explicit_vertex_anthropic_location_wins(monkeypatch: pytest.MonkeyPatch):
    """When the user did set the field, that value is used verbatim."""
    captured = _invoke_anthropic(
        monkeypatch,
        model="claude-3-sonnet@20240229",
        credentials={
            "vertex_project_id": "test-project",
            "vertex_location": "europe-west4",
            "vertex_anthropic_location": "asia-southeast1",
        },
    )
    assert captured.instances[0]["region"] == "asia-southeast1"


def test_missing_locations_fall_back_to_us_east5_for_claude_4_models(monkeypatch: pytest.MonkeyPatch):
    """When neither location is set, the model-name-based default kicks in."""
    for model in US_EAST5_MODELS:
        _CapturedClient.reset()
        captured = _invoke_anthropic(
            monkeypatch,
            model=model,
            credentials={"vertex_project_id": "test-project", "vertex_location": ""},
        )
        assert captured.instances[0]["region"] == "us-east5", (
            f"Expected us-east5 for {model}, got {captured.instances[0]['region']}"
        )


def test_missing_locations_fall_back_to_us_central1_for_older_models(monkeypatch: pytest.MonkeyPatch):
    """Older Claude 3 models default to us-central1 when no location is set."""
    for model in US_CENTRAL_MODELS:
        _CapturedClient.reset()
        captured = _invoke_anthropic(
            monkeypatch,
            model=model,
            credentials={"vertex_project_id": "test-project", "vertex_location": ""},
        )
        assert captured.instances[0]["region"] == "us-central1", (
            f"Expected us-central1 for {model}, got {captured.instances[0]['region']}"
        )


def test_empty_vertex_location_and_empty_vertex_anthropic_location_falls_back_to_model_default(
    monkeypatch: pytest.MonkeyPatch,
):
    """Both location keys present but empty: still falls through to the model default."""
    captured = _invoke_anthropic(
        monkeypatch,
        model="claude-sonnet-4-5@20250929",
        credentials={
            "vertex_project_id": "test-project",
            "vertex_location": "",
            "vertex_anthropic_location": "",
        },
    )
    assert captured.instances[0]["region"] == "us-east5"


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------

def test_llm_reads_vertex_anthropic_location_defensively():
    """Pin the read so a future refactor can't reintroduce the KeyError."""
    source = LLM_PY.read_text()
    # The exact line that previously raised KeyError must now use .get().
    assert 'credentials.get("vertex_anthropic_location")' in source
    # And there must not be a raw `[]` read of the same key still in the file.
    assert 'credentials["vertex_anthropic_location"]' not in source


def test_llm_location_resolution_chain_starts_with_vertex_anthropic_location():
    """The resolution order is preserved: anthropic-specific > general > model default."""
    # The exact ordering string the code uses is the contract: a future
    # refactor that swaps the order would silently change behavior.
    expected_chain = (
        'if vertex_anthropic_location:'
        '\n            location = vertex_anthropic_location'
        '\n        elif vertex_location:'
        '\n            location = vertex_location'
    )
    assert expected_chain in LLM_PY.read_text()