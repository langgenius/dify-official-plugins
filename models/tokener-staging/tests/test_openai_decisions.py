import json
from decimal import Decimal
from hashlib import sha256

import pytest
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeServerUnavailableError
from protocol_http import CREDENTIALS, TOOL, contents
from protocol_http import llm as llm
from protocol_http import registry as registry
from protocol_http import wire as wire

from models.llm._classifier_prompt import QUESTION_CLASSIFIER_SYSTEM_PROMPT
from models.llm._openai_decisions import MODEL, UPSTREAM_MODEL


def classifier_messages(
    query: str = "What is the weather in Seoul?",
    categories: list[dict] | None = None,
    instruction: str = "Pick the best route.",
    histories: str = "Human: hi\\nAssistant: hello",
) -> list:
    items = (
        categories
        if categories is not None
        else [
            {"category_id": "weather", "category_name": "Weather"},
            {"category_id": "billing", "category_name": "Billing"},
        ]
    )
    body = (
        '{"input_text": ["'
        + query
        + '"],\n    "categories": '
        + json.dumps(items, ensure_ascii=False)
        + ',\n    "classification_instructions": ["'
        + instruction
        + '"]}'
    )
    return [
        SystemPromptMessage(
            content=QUESTION_CLASSIFIER_SYSTEM_PROMPT.replace("{histories}", histories)
        ),
        UserPromptMessage(content="I need help with my invoice"),
        AssistantPromptMessage(content='{"category_id": "billing"}'),
        UserPromptMessage(content="Will it snow tomorrow?"),
        AssistantPromptMessage(content='{"category_id": "weather"}'),
        UserPromptMessage(content=[TextPromptMessageContent(data=body)]),
    ]


def decision_payload(
    choice: str = "weather",
    input_tokens: int = 120,
    output_tokens: int = 15,
) -> dict:
    return {
        "id": "dec_test123",
        "object": "decision",
        "created_at": 1767225600,
        "model": UPSTREAM_MODEL,
        "answers": [
            {
                "type": "choice",
                "name": "route",
                "choice": choice,
                "confidence": 0.98,
                "probabilities": {"weather": 0.98, "billing": 0.02},
            }
        ],
        "usage": {
            "input_tokens": input_tokens,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 5},
            "total_tokens": input_tokens + output_tokens,
        },
    }


def test_decisions_classifier_sends_decisions_wire_preserves_backslashes_and_prices_zero_output(
    llm, wire
):
    _, requests, replies = wire
    replies.append((200, {"Content-Type": "application/json"}, decision_payload()))
    messages = classifier_messages(
        query=r"C:\Users\alice\report\nfinal",
        instruction=r"Keep literal \t and \u0041 intact",
        histories=r"path=D:\logs\app.log",
    )
    chunks = list(
        llm.invoke(
            MODEL,
            CREDENTIALS,
            messages,
            {"temperature": 0.7, "response_format": "XML"},
            stream=False,
            user="org-member-42",
        )
    )
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.model == MODEL
    assert json.loads(contents(chunks)) == {
        "category_id": "weather",
        "category_name": "Weather",
    }
    assert chunk.delta.usage.prompt_tokens == 120
    assert chunk.delta.usage.completion_tokens == 15
    assert chunk.delta.usage.prompt_price == Decimal("0.0000120")
    assert chunk.delta.usage.completion_price == Decimal("0")
    assert chunk.delta.usage.total_price == Decimal("0.0000120")

    path, _, body = requests[0]
    assert path == "/v1/decisions"
    assert body["model"] == UPSTREAM_MODEL
    assert body["safety_identifier"] == sha256(b"org-member-42").hexdigest()
    assert json.loads(body["input"]) == {
        "query": r"C:\Users\alice\report\nfinal",
        "history_text": r"path=D:\logs\app.log",
    }
    assert body["questions"] == [
        {
            "type": "choice",
            "name": "route",
            "instructions": (
                "Classify input.query into exactly one provided category, "
                "using input.history_text as conversation context.\n"
                r"Keep literal \t and \u0041 intact"
            ),
            "choices": [
                {"value": "weather", "description": "Weather"},
                {"value": "billing", "description": "Billing"},
            ],
        }
    ]


def test_decisions_classifier_direct_invoke_rejects_parameters_tools_stop_and_bad_templates(
    llm, wire
):
    _, requests, replies = wire
    replies.append((200, {"Content-Type": "application/json"}, decision_payload()))
    valid = classifier_messages()
    ok = llm._invoke(
        MODEL,
        CREDENTIALS,
        valid,
        {"enable_stream": False, "service_tier": ""},
        stream=True,
    )
    assert isinstance(ok, LLMResult)
    assert len(requests) == 1

    with pytest.raises(InvokeBadRequestError):
        llm._invoke(MODEL, CREDENTIALS, valid, {"temperature": 0.2})
    with pytest.raises(InvokeBadRequestError):
        llm._invoke(MODEL, CREDENTIALS, valid, {}, tools=[TOOL])
    with pytest.raises(InvokeBadRequestError):
        llm._invoke(MODEL, CREDENTIALS, valid, {}, stop=["END"])
    with pytest.raises(InvokeBadRequestError):
        list(llm.invoke(MODEL, CREDENTIALS, [UserPromptMessage(content="not a classifier")], {}))
    with pytest.raises(InvokeBadRequestError):
        list(llm.invoke(MODEL, CREDENTIALS, classifier_messages(categories=[]), {}))
    assert len(requests) == 1


@pytest.mark.parametrize(
    "bad_payload",
    [
        {
            "answers": [{"type": "refusal", "name": "route", "refusal": "denied"}],
            "usage": {"input_tokens": 1, "output_tokens": 0},
        },
        {
            "answers": [{"type": "choice", "name": "route", "choice": "unknown"}],
            "usage": {"input_tokens": 1, "output_tokens": 0},
        },
        {"answers": [], "usage": {"input_tokens": 1, "output_tokens": 0}},
        {
            "answers": [{"type": "choice", "name": "route", "choice": "weather"}],
            "usage": {"input_tokens": True, "output_tokens": 0},
        },
    ],
)
def test_decisions_classifier_rejects_refusal_unknown_category_and_invalid_usage(
    llm, wire, bad_payload
):
    _, _, replies = wire
    replies.append((200, {"Content-Type": "application/json"}, bad_payload))
    with pytest.raises(InvokeServerUnavailableError):
        list(llm.invoke(MODEL, CREDENTIALS, classifier_messages(), {}, stream=False))
