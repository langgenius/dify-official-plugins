from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import AssistantPromptMessage, UserPromptMessage
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from google.genai import errors, interactions, types
from google.genai._gaos.lib.compat_errors import APIError as InteractionsAPIError

from models.llm.llm import GoogleLargeLanguageModel


@pytest.fixture(params=["generate_content", "interactions"])
def invocation(request):
    model = (
        "gemini-2.5-flash"
        if request.param == "generate_content"
        else "gemini-3.5-flash"
    )
    schema_path = Path(__file__).parents[1] / "llm" / f"{model}.yaml"
    llm = GoogleLargeLanguageModel(
        [AIModelEntity(**yaml.safe_load(schema_path.read_text()))]
    )
    parameters = (
        {}
        if request.param == "generate_content"
        else {"json_schema": '{"type": "object"}', "grounding": True}
    )
    return (
        llm,
        request.param,
        {
            "model": model,
            "credentials": {"google_api_key": "test-key"},
            "prompt_messages": [UserPromptMessage(content="Hello")],
            "model_parameters": parameters,
        },
    )


def _api_error(code, route):
    body = {
        "error": {
            "code": code,
            "status": "RESOURCE_EXHAUSTED" if code == 429 else "API_ERROR",
            "message": (
                "You exceeded your current quota. " + "quota metric details\n" * 100
                if code == 429
                else "The provider rejected this request."
            ),
            "details": [{"quotaMetric": "raw-response-detail"}],
        }
    }
    if route == "interactions":
        return InteractionsAPIError.generate(
            status_code=code,
            body=body,
            message=None,
            response=httpx.Response(
                code,
                request=httpx.Request("POST", "https://example.com/interactions"),
                json=body,
            ),
        )
    error_class = errors.ServerError if code >= 500 else errors.ClientError
    return error_class(code, body)


def _assert_message(error, code):
    message = str(error)
    assert "raw-response-detail" not in message
    assert "Traceback" not in message
    provider_message = (
        "You exceeded your current quota. " + "quota metric details\n" * 100
        if code == 429
        else "The provider rejected this request."
    )
    assert provider_message in message


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("code", "expected_error"),
    [
        (400, InvokeBadRequestError),
        (401, InvokeAuthorizationError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (500, InvokeServerUnavailableError),
        (503, InvokeServerUnavailableError),
    ],
)
def test_immediate_api_error_uses_status_and_message(
    invocation, stream, code, expected_error
):
    llm, route, kwargs = invocation
    client = Mock()
    method = (
        client.interactions.create
        if route == "interactions"
        else client.models.generate_content_stream
        if stream
        else client.models.generate_content
    )
    method.side_effect = _api_error(code, route)

    with patch("models.llm.llm.genai.Client", return_value=client):
        with pytest.raises(expected_error) as raised:
            list(llm.invoke(**kwargs, stream=stream))

    method.assert_called_once()
    _assert_message(raised.value, code)


@pytest.mark.parametrize("after_chunk", [False, True])
def test_rate_limit_during_stream_iteration_is_normalized(invocation, after_chunk):
    llm, route, kwargs = invocation
    client = Mock()

    def response():
        if after_chunk:
            if route == "interactions":
                yield interactions.StepDelta(
                    index=0, delta=interactions.TextDelta(text="Partial response")
                )
            else:
                yield types.GenerateContentResponse(
                    candidates=[
                        types.Candidate(
                            content=types.Content(
                                role="model",
                                parts=[types.Part(text="Partial response")],
                            )
                        )
                    ]
                )
        raise _api_error(429, route)

    method = (
        client.interactions.create
        if route == "interactions"
        else client.models.generate_content_stream
    )
    method.return_value = response()

    with patch("models.llm.llm.genai.Client", return_value=client):
        result = llm.invoke(**kwargs)
        if after_chunk:
            chunk = next(result)
            assert isinstance(chunk, LLMResultChunk)
            assert chunk.delta.message.content[0].data == "Partial response"
        with pytest.raises(InvokeRateLimitError) as raised:
            next(result)

    _assert_message(raised.value, 429)


@pytest.mark.parametrize("during_iteration", [False, True])
def test_existing_invoke_error_is_preserved(invocation, during_iteration):
    llm, _, kwargs = invocation
    error = InvokeBadRequestError("Invalid prompt content")

    def response():
        yield LLMResultChunk(
            model=kwargs["model"],
            prompt_messages=kwargs["prompt_messages"],
            delta=LLMResultChunkDelta(
                index=0, message=AssistantPromptMessage(content="Partial response")
            ),
        )
        raise error

    with patch.object(llm, "_generate") as generate:
        if during_iteration:
            generate.return_value = response()
        else:
            generate.side_effect = error
        with pytest.raises(InvokeBadRequestError) as raised:
            list(llm.invoke(**kwargs))

    assert raised.value is error
    assert str(raised.value) == "Invalid prompt content"
