import json
from unittest.mock import patch

import pytest
import requests
from dify_plugin.errors.model import CredentialsValidateFailedError

from models.llm.llm import NVIDIA_BUILD_DEFAULT_URL, NVIDIANIMProvider


def response(status: int, payload: object) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = (
        payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    )
    result.headers["Content-Type"] = "application/json"
    return result


def catalog_payload(model_ids: list[str]) -> dict:
    return {"object": "list", "data": [{"id": m} for m in model_ids]}


def credentials(**overrides) -> dict:
    base = {
        "api_key": "nvapi-test",
        "endpoint_url": NVIDIA_BUILD_DEFAULT_URL,
        "mode": "chat",
    }
    base.update(overrides)
    return base


def make_provider() -> NVIDIANIMProvider:
    return NVIDIANIMProvider.__new__(NVIDIANIMProvider)


PING_OK = response(
    200, {"object": "chat.completion", "choices": [{"message": {"content": "ping"}}]}
)
BUILD_MODEL = "deepseek-ai/deepseek-v4.1-flash"


def assert_ping(post, model: str = BUILD_MODEL, api_key: str = "nvapi-test") -> None:
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == f"{NVIDIA_BUILD_DEFAULT_URL}/chat/completions"
    assert kwargs["headers"]["Authorization"] == f"Bearer {api_key}"
    assert kwargs["json"]["model"] == model
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "ping"}]


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_empty_endpoint_falls_back_to_build_catalog(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, catalog_payload([BUILD_MODEL]))

    provider.validate_credentials(BUILD_MODEL, credentials(endpoint_url=""))

    get.assert_called_once_with(
        f"{NVIDIA_BUILD_DEFAULT_URL}/models",
        headers={"Accept": "application/json", "Authorization": "Bearer nvapi-test"},
        timeout=(5, 10),
        allow_redirects=False,
    )
    assert_ping(post)


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_trailing_slash_does_not_duplicate_path(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, catalog_payload(["m1"]))

    provider.validate_credentials(
        "m1", credentials(api_key="", endpoint_url="https://host/v1/")
    )

    get.assert_called_once_with(
        "https://host/v1/models",
        headers={"Accept": "application/json"},
        timeout=(5, 10),
        allow_redirects=False,
    )
    post.assert_called_once()
    assert post.call_args.args[0] == "https://host/v1/chat/completions"


@patch("dify_plugin.interfaces.model.openai_compatible.llm.requests.post")
@patch("models.llm.llm.requests.get")
def test_unknown_model_raises_with_suggestion(get, post) -> None:
    provider = make_provider()
    get.return_value = response(
        200, catalog_payload([BUILD_MODEL, "meta/llama-3.1-8b"])
    )

    with pytest.raises(
        CredentialsValidateFailedError, match="Did you mean: .*deepseek"
    ):
        provider.validate_credentials("deepseek-ai/deepseek-v4.1-flsh", credentials())

    post.assert_not_called()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_unknown_model_on_custom_endpoint_is_soft(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, catalog_payload(["listed-model"]))

    provider.validate_credentials(
        "unlisted-model", credentials(api_key="", endpoint_url="https://nim.local/v1")
    )

    post.assert_called_once()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_non_string_model_ids_do_not_crash(get, post) -> None:
    provider = make_provider()
    get.return_value = response(
        200, {"data": [{"id": 123}, {"id": True}, {"id": "ok-model"}]}
    )

    provider.validate_credentials(
        "ok-model", credentials(api_key="", endpoint_url="https://nim.local/v1")
    )

    post.assert_called_once()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_custom_endpoint_without_models_endpoint_falls_back_to_ping(get, post) -> None:
    provider = make_provider()
    get.return_value = response(404, {"error": {"message": "not found"}})

    provider.validate_credentials(
        "local-model", credentials(endpoint_url="https://nim.local/v1")
    )

    post.assert_called_once()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_empty_model_list_is_soft(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, catalog_payload([]))

    provider.validate_credentials(
        "any-model", credentials(endpoint_url="https://nim.local/v1")
    )

    post.assert_called_once()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_malformed_catalog_payload_is_soft(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, {"unexpected": True})

    provider.validate_credentials(
        "any-model", credentials(endpoint_url="https://nim.local/v1")
    )

    post.assert_called_once()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_api_key_whitespace_is_normalized(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, catalog_payload([BUILD_MODEL]))

    provider.validate_credentials(BUILD_MODEL, credentials(api_key="  nvapi-test  "))

    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer nvapi-test"
    assert_ping(post, api_key="nvapi-test")


@patch("dify_plugin.interfaces.model.openai_compatible.llm.requests.post")
@patch("models.llm.llm.requests.get")
def test_build_catalog_requires_api_key(get, post) -> None:
    provider = make_provider()

    with pytest.raises(CredentialsValidateFailedError, match="API Key is required"):
        provider.validate_credentials("some-model", credentials(api_key=""))

    get.assert_not_called()
    post.assert_not_called()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=response(401, {"error": "unauthorized"}),
)
@patch("models.llm.llm.requests.get")
def test_invalid_key_fails_on_ping(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, catalog_payload(["m1"]))

    with pytest.raises(CredentialsValidateFailedError):
        provider.validate_credentials("m1", credentials())

    get.assert_called_once()
    post.assert_called_once()


@patch(
    "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
    return_value=PING_OK,
)
@patch("models.llm.llm.requests.get")
def test_missing_mode_defaults_to_chat(get, post) -> None:
    provider = make_provider()
    get.return_value = response(200, catalog_payload([BUILD_MODEL]))

    provider.validate_credentials(BUILD_MODEL, credentials(endpoint_url="", mode=None))

    assert_ping(post)
