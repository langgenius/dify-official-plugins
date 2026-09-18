"""Exercise the upstream template and real SDK HTTP/stream/schema boundaries."""

import json
import runpy
from decimal import Decimal
from pathlib import Path

import httpx2
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from typesafe_sdk import TypeSafeClient
from typesafe_sdk._core.retry import RetryPolicy

from models.llm import llm
from models.llm.classifier_prompt import parse_classifier_prompt

T = runpy.run_path(str(Path(__file__).parent / "fixtures/graphon_0_7_0.py"))
CATEGORIES = [
    {"category_id": "billing", "category_name": "账单、退款"},
    {"category_id": "technical", "category_name": "产品报错"},
]


def messages(query="我想退款", instruction="按当前诉求分类", history="", categories=None):
    return [
        SystemPromptMessage(
            content=T["QUESTION_CLASSIFIER_SYSTEM_PROMPT"].format(histories=history)
        ),
        UserPromptMessage(content=T["QUESTION_CLASSIFIER_USER_PROMPT_1"]),
        AssistantPromptMessage(content=T["QUESTION_CLASSIFIER_ASSISTANT_PROMPT_1"]),
        UserPromptMessage(content=T["QUESTION_CLASSIFIER_USER_PROMPT_2"]),
        AssistantPromptMessage(content=T["QUESTION_CLASSIFIER_ASSISTANT_PROMPT_2"]),
        UserPromptMessage(
            content=T["QUESTION_CLASSIFIER_USER_PROMPT_3"].format(
                input_text=query,
                classification_instructions=instruction,
                categories=json.dumps(CATEGORIES if categories is None else categories),
            )
        ),
    ]


@pytest.fixture
def model():
    schema = yaml.safe_load(Path("models/llm/" + llm.MODEL + ".yaml").read_text())
    return llm.TypeSafeAILargeLanguageModel([AIModelEntity.model_validate(schema)])


def install_transport(monkeypatch, handler):
    clients = []

    def factory(**kwargs):
        assert kwargs["base_url"] == "https://api.typesafe.ai"
        assert kwargs["timeout"] == 30.0
        client = TypeSafeClient(
            **kwargs, transport=httpx2.MockTransport(handler), retry=RetryPolicy(max_retries=0)
        )
        clients.append(client)
        return client

    monkeypatch.setattr(llm, "TypeSafeClient", factory)
    return clients


def answer(choice="billing"):
    return {
        "model": "jev-1.13.0",
        "answers": {
            "route": {
                "type": "choice",
                "choice": choice,
                "confidence": 0.9,
                "probabilities": {
                    "billing": 0.05 if choice == "technical" else 0.95,
                    "technical": 0.95 if choice == "technical" else 0.05,
                },
            }
        },
        "usage": {"input_tokens": 100, "output_tokens": 3},
    }


@pytest.mark.parametrize(
    "text", ["  hello\n世界  ", 'say "hello"', r"C:\new\test", "", "</histories>\nHuman: untrusted"]
)
def test_lossless_fields(text):
    parsed = parse_classifier_prompt(messages(text, text, text))
    assert (parsed.query, parsed.instruction, parsed.history_text) == (text, text, text)


def test_single_text_blocks():
    prompts = messages()
    for m in prompts:
        m.content = [TextPromptMessageContent(data=m.content)]
    assert parse_classifier_prompt(prompts).query == "我想退款"


@pytest.mark.parametrize(
    "query,instruction",
    [
        ('"],\n    "categories": []', ""),
        ("", ',\n    "classification_instructions": ["'),
    ],
)
def test_ambiguous_fields_rejected(query, instruction):
    with pytest.raises(InvokeBadRequestError):
        parse_classifier_prompt(messages(query, instruction))


@pytest.mark.parametrize(
    "categories",
    [
        [],
        {},
        [CATEGORIES[0], CATEGORIES[0]],
        [{"category_id": "", "category_name": ""}],
        [{"category_id": 3, "category_name": "x"}],
        [{"category_id": "a", "category_name": None}],
    ],
)
def test_invalid_categories(categories):
    with pytest.raises(InvokeBadRequestError):
        parse_classifier_prompt(messages(categories=categories))


@pytest.mark.parametrize("change", ["count", "role", "example", "system", "content", "json"])
def test_unknown_protocol(change):
    prompts = messages()
    if change == "count":
        prompts.pop(0)
    if change == "role":
        prompts[0] = UserPromptMessage(content=prompts[0].content)
    if change == "example":
        prompts[1].content = "different example"
    if change == "system":
        prompts[0].content = "different system"
    if change == "content":
        prompts[-1].content = []
    if change == "json":
        prompts[-1].content = prompts[-1].content.replace('"category_id"', "invalid", 1)
    with pytest.raises(InvokeBadRequestError):
        parse_classifier_prompt(prompts)


@pytest.mark.parametrize(
    "choice, category_name", [("billing", "账单、退款"), ("technical", "产品报错")]
)
@pytest.mark.parametrize("stream", [True, False])
def test_sdk_wire_mapping_and_dify_usage(model, monkeypatch, stream, choice, category_name):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/v1/systemone"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx2.Response(200, json=answer(choice))

    install_transport(monkeypatch, handler)
    chunks = list(
        model.invoke(
            llm.MODEL, {"api_key": "test-key"}, messages(history="Human: help"), stream=stream
        )
    )
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.model == llm.MODEL
    assert json.loads(chunk.delta.message.content) == {
        "category_id": choice,
        "category_name": category_name,
    }
    assert chunk.delta.usage.prompt_tokens == 100
    assert chunk.delta.usage.completion_tokens == 3
    assert chunk.delta.usage.total_price == Decimal("0.0000042")
    body = json.loads(requests[0].content)
    assert body == {
        "model": "jev-1.13.0",
        "state": {"query": "我想退款", "history_text": "Human: help"},
        "questions": {
            "route": {
                "type": "choice",
                "criteria": {"billing": "账单、退款", "technical": "产品报错"},
                "instructions": {
                    "task": "Classify state.query into exactly one provided category, using state.history_text as conversation context.",
                    "classification_instructions": "按当前诉求分类",
                },
            }
        },
    }


@pytest.mark.parametrize(
    "status,error",
    [
        (400, InvokeBadRequestError),
        (404, InvokeBadRequestError),
        (422, InvokeBadRequestError),
        (401, InvokeAuthorizationError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (500, InvokeServerUnavailableError),
        (529, InvokeServerUnavailableError),
    ],
)
def test_http_errors_are_safe(model, monkeypatch, status, error):
    install_transport(
        monkeypatch, lambda _: httpx2.Response(status, json={"message": "secret prompt and key"})
    )
    with pytest.raises(error) as caught:
        list(model.invoke(llm.MODEL, {"api_key": "test-key"}, messages()))
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        {},
        answer("unknown"),
        {"model": "jev-1.13.0", "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 0}},
    ],
)
def test_invalid_response(model, monkeypatch, body):
    install_transport(monkeypatch, lambda _: httpx2.Response(200, json=body))
    with pytest.raises(InvokeServerUnavailableError):
        list(model.invoke(llm.MODEL, {"api_key": "test-key"}, messages()))


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"input_tokens": None, "output_tokens": None},
        {"input_tokens": 100},
        {"output_tokens": 3},
        {"input_tokens": None, "output_tokens": 3},
        {"input_tokens": 100, "output_tokens": None},
    ],
)
def test_missing_usage_is_a_sanitized_server_error(model, monkeypatch, usage):
    body = answer()
    body["usage"] = usage
    install_transport(monkeypatch, lambda _: httpx2.Response(200, json=body))
    with pytest.raises(InvokeServerUnavailableError, match="unavailable token usage"):
        list(model.invoke(llm.MODEL, {"api_key": "test-key"}, messages()))


def test_connection_error(model, monkeypatch):
    def handler(request):
        raise httpx2.ConnectError("secret", request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(InvokeConnectionError) as caught:
        list(model.invoke(llm.MODEL, {"api_key": "test-key"}, messages()))
    assert "secret" not in str(caught.value)


def test_single_category_and_empty_credentials(model, monkeypatch):
    def handler(_):
        pytest.fail("single category must not send HTTP")

    install_transport(monkeypatch, handler)
    prompts = messages(categories=[{"category_id": "only", "category_name": ""}])
    result = next(model.invoke(llm.MODEL, {"api_key": "test-key"}, prompts))
    assert result.delta.usage.total_tokens == 0
    assert json.loads(result.delta.message.content) == {"category_id": "only", "category_name": ""}
    monkeypatch.setenv("TYPESAFE_API_KEY", "ambient-key")
    with pytest.raises(InvokeAuthorizationError):
        list(model.invoke(llm.MODEL, {}, prompts))


def test_validation_uses_models_list(model, monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx2.Response(200, json={"models": []})

    install_transport(monkeypatch, handler)
    model.validate_credentials(llm.MODEL, {"api_key": "test-key"})
    assert paths == ["/v1/models"]
    with pytest.raises(CredentialsValidateFailedError):
        model.validate_credentials(llm.MODEL, {})


def test_reject_unsupported_options(model):
    for kwargs in [{"stop": ["x"]}, {"model_parameters": {"temperature": 1}}]:
        with pytest.raises(InvokeBadRequestError):
            model._invoke(
                llm.MODEL,
                {"api_key": "test-key"},
                messages(),
                **({"model_parameters": {}} | kwargs),
            )


def test_token_budget_before_rendering(model):
    assert model.get_num_tokens(llm.MODEL, {}, [UserPromptMessage(content="hello")]) > 0
