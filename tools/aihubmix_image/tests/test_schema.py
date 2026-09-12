"""Payload building is schema-driven, so the fixtures are the specification.

Every fixture is a real endpoint-discovery document captured from the gateway. The rule the
tests enforce is the one the gateway enforces: the request body may only contain fields the
model declares, because the unified endpoint sets additionalProperties: false.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.client import GatewayError  # noqa: E402
from utils.schema import _select_unified_endpoint, build_payload, parse_extra  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
MODELS = sorted(p.stem for p in FIXTURES.glob("*.json") if not p.name.startswith("_"))


def endpoint_for(model: str):
    document = json.loads((FIXTURES / f"{model}.json").read_text())
    return _select_unified_endpoint(document, model)


def test_every_fixture_exposes_a_unified_endpoint():
    assert MODELS, "fixtures are missing"
    for model in MODELS:
        endpoint = endpoint_for(model)
        assert endpoint.path == "/ai/v1/images/generations"
        assert endpoint.method == "POST"


@pytest.mark.parametrize("model", MODELS)
def test_payload_only_contains_declared_fields(model):
    endpoint = endpoint_for(model)
    payload, _ = build_payload(
        endpoint,
        prompt="a red bicycle",
        scalars={"n": 1, "size": "1024x1024", "seed": 7, "negative_prompt": "blurry"},
        media={},
        extra={},
    )
    assert set(payload) <= set(endpoint.properties)
    assert payload["model"] == endpoint.model
    assert payload["prompt"] == "a red bicycle"


def test_unsupported_scalar_is_dropped_and_reported():
    # mai-image-2.6-flash rejects n with HTTP 400; it must never reach the gateway.
    endpoint = endpoint_for("mai-image-2.6-flash")
    assert not endpoint.declares("n")
    payload, notes = build_payload(
        endpoint, prompt="hi", scalars={"n": 3}, media={}, extra={}
    )
    assert "n" not in payload
    assert any("'n' ignored" in note for note in notes)


def test_size_wins_over_aspect_ratio():
    endpoint = endpoint_for("doubao-seedream-4-5")
    payload, notes = build_payload(
        endpoint,
        prompt="hi",
        scalars={"size": "2048x2048", "aspect_ratio": "16:9"},
        media={},
        extra={},
    )
    assert payload["size"] == "2048x2048"
    assert "aspect_ratio" not in payload
    assert any("aspect_ratio" in note for note in notes)


def test_enum_violation_names_the_allowed_values():
    endpoint = endpoint_for("gpt-image-2")
    with pytest.raises(GatewayError) as excinfo:
        build_payload(
            endpoint, prompt="hi", scalars={"output_format": "webp"}, media={}, extra={}
        )
    message = str(excinfo.value)
    assert "png" in message and "jpeg" in message


def test_size_pattern_is_checked_locally():
    endpoint = endpoint_for("gpt-image-2")
    with pytest.raises(GatewayError):
        build_payload(endpoint, prompt="hi", scalars={"size": "huge"}, media={}, extra={})
    payload, _ = build_payload(
        endpoint, prompt="hi", scalars={"size": "auto"}, media={}, extra={}
    )
    assert payload["size"] == "auto"


def test_numbers_arrive_as_numbers():
    endpoint = endpoint_for("gpt-image-2")
    payload, _ = build_payload(endpoint, prompt="hi", scalars={"n": "2"}, media={}, extra={})
    assert payload["n"] == 2


def test_range_violation_is_rejected():
    endpoint = endpoint_for("gpt-image-2")
    with pytest.raises(GatewayError):
        build_payload(endpoint, prompt="hi", scalars={"n": 99}, media={}, extra={})


def test_extra_is_routed_to_the_vendor_passthrough():
    endpoint = endpoint_for("gpt-image-2")
    payload, notes = build_payload(
        endpoint, prompt="hi", scalars={}, media={}, extra={"quality": "high"}
    )
    assert payload["extra"] == {"quality": "high"}
    assert not notes


def test_extra_key_declared_at_top_level_stays_at_top_level():
    # webhook_url is a top-level field on every model, quality lives inside extra on this one.
    endpoint = endpoint_for("gpt-image-2")
    payload, _ = build_payload(
        endpoint,
        prompt="hi",
        scalars={},
        media={},
        extra={"webhook_url": "https://example.com/hook", "quality": "low"},
    )
    assert payload["webhook_url"] == "https://example.com/hook"
    assert payload["extra"] == {"quality": "low"}


def test_unknown_extra_key_is_reported_with_the_accepted_list():
    endpoint = endpoint_for("gpt-image-2")
    _, notes = build_payload(
        endpoint, prompt="hi", scalars={}, media={}, extra={"nonsense": 1}
    )
    assert any("nonsense" in note and "accepts" in note for note in notes)


def test_missing_required_field_says_what_it_accepts():
    # agnes-image-2.1-flash cannot be called without a size.
    endpoint = endpoint_for("agnes-image-2.1-flash")
    with pytest.raises(GatewayError) as excinfo:
        build_payload(endpoint, prompt="hi", scalars={}, media={}, extra={})
    assert "size" in str(excinfo.value) and "x" in str(excinfo.value)

    payload, _ = build_payload(endpoint, prompt="hi", scalars={"size": "2K"}, media={}, extra={})
    assert payload["size"] == "2K"


def test_a_missing_field_is_explained_in_the_model_own_words():
    """The pattern alone reads as line noise in the tool panel, so the message carries the
    field description the gateway publishes alongside it."""
    endpoint = endpoint_for("agnes-image-2.1-flash")
    description = endpoint.properties["size"]["description"]
    with pytest.raises(GatewayError) as excinfo:
        build_payload(endpoint, prompt="hi", scalars={}, media={}, extra={})
    assert description in str(excinfo.value)


def test_prompt_is_required():
    endpoint = endpoint_for("glm-image")
    with pytest.raises(GatewayError):
        build_payload(endpoint, prompt="   ", scalars={}, media={}, extra={})


def test_parse_extra_rejects_non_objects():
    assert parse_extra("") == {}
    assert parse_extra('{"a": 1}') == {"a": 1}
    with pytest.raises(GatewayError):
        parse_extra("[1, 2]")
    with pytest.raises(GatewayError):
        parse_extra("not json")
