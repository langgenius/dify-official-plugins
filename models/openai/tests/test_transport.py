import json

import httpx
import openai
import pytest

from models.common_openai import _CommonOpenAI


@pytest.mark.parametrize(
    ("controls", "expected"),
    [
        ({}, {}),
        ({"max_retries": "", "request_timeout": None}, {}),
        ({"max_retries": "0", "request_timeout": "12.5"}, {"max_retries": 0, "timeout": 12.5}),
    ],
)
def test_transport_credentials_preserve_defaults_and_explicit_zero(controls, expected):
    assert _CommonOpenAI()._to_credential_kwargs({"openai_api_key": "key", **controls}) == {
        "api_key": "key",
        **expected,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [("max_retries", v) for v in (-1, 0.5, True, "bad", float("inf"))]
    + [("request_timeout", v) for v in (0, -1, True, "bad", float("nan"), float("inf"))],
)
def test_invalid_transport_credentials_fail_before_client_creation(name, value):
    with pytest.raises(ValueError, match=name):
        _CommonOpenAI()._to_credential_kwargs({"openai_api_key": "key", name: value})


@pytest.mark.parametrize("protocol", ["responses", "chat"])
@pytest.mark.parametrize("failure", [500, 429, "timeout"])
@pytest.mark.parametrize(("retries", "attempts"), [(0, 1), (1, 2), (None, 3)])
def test_actual_sdk_transport_obeys_retry_and_timeout_controls(
    protocol, failure, retries, attempts, llm, mocker, prompt_messages
):
    observed = []

    def handle(request):
        observed.append(request)
        assert request.extensions["timeout"]["read"] == 12.5
        assert json.loads(request.content)["model"] == "gpt-6-luna"
        if failure == "timeout":
            raise httpx.ReadTimeout("controlled timeout", request=request)
        return httpx.Response(failure, json={"error": {"message": "controlled failure"}})

    credentials = {
        "openai_api_key": "local-test-key",
        "openai_api_base": "https://example.test/v1",
        "api_protocol": protocol,
        "request_timeout": "12.5",
    }
    if retries is not None:
        credentials["max_retries"] = str(retries)
    mocker.patch("openai._base_client.time.sleep")
    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        mocker.patch(
            "models.llm.llm.OpenAI",
            side_effect=lambda **kwargs: openai.OpenAI(http_client=http_client, **kwargs),
        )
        with pytest.raises(openai.APIError):
            llm._chat_generate(
                "gpt-6-luna", credentials, prompt_messages, {}, None, None, False, None
            )
    assert len(observed) == attempts
