import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.llm._functional import (
    convert_finish_reason,
    generation_options,
    merge_consecutive_messages,
    normalize_anthropic_endpoint,
    parse_json_object,
    render_assistant_text,
    resolve_model_name,
    user_content_block,
)


def test_generation_options_are_immutable_and_data_driven() -> None:
    parameters = {
        "max_output_tokens": 2048,
        "thinking": "adaptive",
        "exclude_reasoning_tokens": False,
        "temperature": 0,
        "top_p": None,
    }
    original = deepcopy(parameters)

    options = generation_options(parameters, "MiniMax-M3")

    assert parameters == original
    assert options.max_tokens == 2048
    assert options.thinking == "adaptive"
    assert options.exclude_reasoning_tokens is False
    assert options.sampling == (("temperature", 0),)


def test_generation_options_follow_alias_precedence_and_m3_defaults() -> None:
    options = generation_options(
        {"max_tokens": 4096, "max_tokens_to_sample": 2048, "max_output_tokens": 1024}, "MiniMax-M3"
    )

    assert options.max_tokens == 4096
    assert options.exclude_reasoning_tokens is True


def test_model_and_finish_reason_dispatch_are_table_driven() -> None:
    assert resolve_model_name("MINIMAX-M3") == "MiniMax-M3"
    assert resolve_model_name("custom-model") == "custom-model"
    assert convert_finish_reason("tool_use") == "tool_calls"
    assert convert_finish_reason("custom") == "custom"
    assert convert_finish_reason(None) is None


def test_content_conversion_accepts_mapping_and_object_shapes() -> None:
    assert user_content_block(
        {"type": "document_url", "document_url": {"url": "https://example.com/report.pdf"}}
    ) == {"type": "document", "source": {"type": "url", "url": "https://example.com/report.pdf"}}
    assert user_content_block(SimpleNamespace(type="image", data="data:image/png;base64,AAAA")) == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"},
    }
    assert user_content_block({"type": "unknown", "data": "ignored"}) is None


def test_message_grouping_does_not_mutate_inputs() -> None:
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "one"}]},
        {"role": "user", "content": "two"},
        {"role": "assistant", "content": [{"type": "text", "text": "three"}]},
    ]
    original = deepcopy(messages)

    grouped = merge_consecutive_messages(messages)

    assert messages == original
    assert grouped == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "three"}]},
    ]


def test_reasoning_rendering_is_a_pure_visibility_policy() -> None:
    thinking = [{"type": "thinking", "thinking": "reason"}, {"type": "redacted_thinking"}]
    answer = ["Visible", " answer"]

    assert render_assistant_text(thinking, answer, hide_thinking=True) == "Visible answer"
    assert render_assistant_text(thinking, answer, hide_thinking=False) == (
        "<think>reason[Redacted thinking]</think>\nVisible answer"
    )


def test_endpoint_and_json_normalization_are_total_functions() -> None:
    assert normalize_anthropic_endpoint("api.example.com/") == ("https://api.example.com/anthropic")
    assert normalize_anthropic_endpoint("https://api.example.com/anthropic") == (
        "https://api.example.com/anthropic"
    )
    assert parse_json_object('{"query":"m3"}') == {"query": "m3"}
    assert parse_json_object("[1,2]") == {"value": [1, 2]}
    assert parse_json_object("not json") == {"raw": "not json"}
