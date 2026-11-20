import json
from decimal import Decimal
from pathlib import Path

import anthropic
import httpx2
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage
from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel


@pytest.fixture(params=[False, True], ids=["blocking", "streaming"])
def billed_usage(request, monkeypatch):
    stream = request.param

    def invoke(
        usage,
        *,
        model="claude-fable-5-2",
        start=None,
        delta=None,
        text="ok",
        reason="end_turn",
        category=None,
    ):
        path = Path(__file__).parents[1] / "models" / "llm" / f"{model}.yaml"
        provider = AnthropicLargeLanguageModel([AIModelEntity(**yaml.safe_load(path.read_text()))])
        details = {"type": "refusal", "category": category} if reason == "refusal" else None
        message = {
            "id": "msg_1",
            "model": model,
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": text}] if text else [],
            "stop_reason": reason,
            "stop_details": details,
            "usage": usage,
        }

        def reply(_request):
            if not stream:
                return httpx2.Response(200, json=message)
            events = [
                {
                    "type": "message_start",
                    "message": {
                        **message,
                        "content": [],
                        "stop_reason": None,
                        "stop_details": None,
                        "usage": start or usage,
                    },
                }
            ]
            if text:
                events.extend(
                    [
                        {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {"type": "text", "text": ""},
                        },
                        {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": text},
                        },
                        {"type": "content_block_stop", "index": 0},
                    ]
                )
            events.extend(
                [
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": reason, "stop_details": details},
                        "usage": delta or {"output_tokens": usage["output_tokens"]},
                    },
                    {"type": "message_stop"},
                ]
            )
            body = "".join(
                f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
            )
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

        with anthropic.Anthropic(
            api_key="test",
            http_client=httpx2.Client(transport=httpx2.MockTransport(reply), trust_env=False),
        ) as client:
            monkeypatch.setattr(llm_module, "Anthropic", lambda **_: client)
            chunks = list(
                provider.invoke(
                    model=model,
                    credentials={"anthropic_api_key": "test"},
                    model_parameters={"max_tokens": 64},
                    prompt_messages=[UserPromptMessage(content="test")],
                    stream=stream,
                )
            )
        return chunks[-1].delta.usage

    return invoke


def test_final_counts_override_start_and_clear_cache_tokens(billed_usage):
    final = {
        "input_tokens": 300,
        "output_tokens": 5,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    start = {
        "input_tokens": 10,
        "output_tokens": 1,
        "cache_creation_input_tokens": 8,
        "cache_read_input_tokens": 20,
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 8},
    }
    usage = billed_usage(final, start=start, delta=final)
    assert (usage.prompt_tokens, usage.completion_tokens) == (300, 5)
    assert usage.prompt_price == Decimal("0.0024")
    assert usage.total_price == Decimal("0.0026")


def test_workspace_us_pricing_stacks_with_fast_and_cache(billed_usage):
    usage = billed_usage(
        {
            "input_tokens": 100,
            "output_tokens": 5,
            "inference_geo": "us",
            "speed": "fast",
            "cache_creation_input_tokens": 4,
            "cache_read_input_tokens": 20,
            "cache_creation": {"ephemeral_5m_input_tokens": 1, "ephemeral_1h_input_tokens": 3},
        }
    )
    assert (usage.prompt_tokens, usage.completion_tokens) == (124, 5)
    assert (usage.prompt_unit_price, usage.completion_unit_price) == (Decimal("17.60"), 88)
    assert usage.prompt_price == Decimal("0.0018964")
    assert usage.total_price == Decimal("0.0023364")


@pytest.mark.parametrize(
    ("model", "input_rate"),
    [("claude-opus-4-6", "5.50"), ("claude-sonnet-4-5", "3.00"), ("claude-opus-5-5", "8.80")],
)
def test_geo_and_speed_apply_to_supported_models(billed_usage, model, input_rate):
    usage = billed_usage(
        {"input_tokens": 1000, "output_tokens": 2, "inference_geo": "us", "speed": "fast"},
        model=model,
    )
    assert usage.prompt_unit_price == Decimal(input_rate)


@pytest.mark.parametrize(("reads", "rate"), [(100, "0.11"), (101, "0.55")])
def test_haiku_us_long_context_counts_cached_input(billed_usage, reads, rate):
    usage = billed_usage(
        {
            "input_tokens": 99_900,
            "cache_read_input_tokens": reads,
            "output_tokens": 1,
            "inference_geo": "us",
        },
        model="claude-haiku-5-5",
    )
    assert usage.prompt_unit_price == Decimal(rate)
    assert usage.completion_unit_price == Decimal(rate) * 5
    assert usage.prompt_price == (99_900 + reads * Decimal("0.1")) * Decimal(rate) / 1_000_000


@pytest.mark.parametrize(
    ("category", "text", "charge"),
    [
        (None, "", "0"),
        ("cyber", "", "0"),
        ("general_harms", "", "0"),
        ("bio", "", "0.010"),
        ("frontier_llm", "", "0.010"),
        ("reasoning_extraction", "", "0.010"),
        ("cyber", "Partial reply", "0.01004"),
    ],
)
def test_refusal_keeps_token_counts_and_applies_documented_charge(
    billed_usage, category, text, charge
):
    usage = billed_usage(
        {"input_tokens": 1250, "output_tokens": int(bool(text))},
        reason="refusal",
        category=category,
        text=text,
    )
    assert (usage.prompt_tokens, usage.completion_tokens) == (1250, int(bool(text)))
    assert usage.total_price == Decimal(charge)
