import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMPollingStatus, LLMUsage
from dify_plugin.entities.model.message import (
    AudioPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError

from models.llm import llm as llm_module
from models.llm.llm import (
    BytePlusArkLargeLanguageModel,
    ArkCredentials,
    ArkHTTPError,
    ArkObjectResponse,
    build_chat_completion_request,
    chat_stream_options_from_parameters,
)


def make_model() -> BytePlusArkLargeLanguageModel:
    return BytePlusArkLargeLanguageModel(model_schemas=[])


def credentials() -> dict[str, str]:
    return {
        "ark_api_key": "test-key",
        "api_endpoint_host": "https://ark.ap-southeast.bytepluses.com/api/v3",
    }


@dataclass(frozen=True)
class CapturedRequest:
    method: str
    path: str
    payload: Any | None = None

    @classmethod
    def from_kwargs(cls, kwargs: dict[str, Any]) -> "CapturedRequest":
        return cls(
            method=kwargs["method"],
            path=kwargs["path"],
            payload=kwargs.get("payload"),
        )

    def payload_dict(self) -> dict[str, Any]:
        assert self.payload is not None
        return self.payload.to_payload()


def provider_response(kwargs: dict[str, Any], payload: dict[str, Any]) -> Any:
    try:
        return kwargs["response_model"].model_validate(payload)
    except Exception as error:
        context = kwargs.get("response_context", "Invalid provider response")
        raise InvokeError(f"{context}: {error}") from error


def test_get_num_tokens_counts_text_from_multimodal_prompt() -> None:
    model = make_model()
    prompt_text = "make a calm ocean video with detailed camera movement"

    token_count = model.get_num_tokens(
        model="seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data=prompt_text),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/frame.png",
                    ),
                ],
            )
        ],
    )

    assert token_count == max(1, len(prompt_text) // 4)


def test_chat_completion_request_is_pydantic_modeled() -> None:
    request = build_chat_completion_request(
        model="seed-1-6-251215",
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="describe this frame"),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/frame.png",
                    ),
                ],
            )
        ],
        model_parameters={"temperature": 0.5, "thinking": "disabled"},
        tools=None,
        stop=["done"],
        user="user-1",
        stream_options=chat_stream_options_from_parameters(
            {"stream_options": {"include_usage": True}}
        ),
    )

    assert request.to_payload() == {
        "model": "seed-1-6-251215",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this frame"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://example.com/frame.png",
                            "detail": "low",
                        },
                    },
                ],
            }
        ],
        "temperature": 0.5,
        "stop": ["done"],
        "user": "user-1",
        "thinking": {"type": "disabled"},
        "reasoning_effort": "minimal",
        "stream_options": {"include_usage": True},
    }


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"ok": true}'


def test_request_model_uses_configured_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests = []

    def fake_urlopen(request: Any, timeout: int) -> FakeResponse:
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(llm_module, "urlopen", fake_urlopen)

    response = model.request_model(
        credentials=ArkCredentials(**credentials()),
        method="GET",
        path="images/generations",
        response_model=ArkObjectResponse,
        response_context="Invalid test response",
    )

    assert response.model_extra == {"ok": True}
    assert (
        requests[0][0].full_url
        == "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"
    )
    assert requests[0][0].get_header("Authorization") == "Bearer test-key"
    assert requests[0][1] == 60


def test_seedance_validate_credentials_uses_non_generation_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"data": []})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    model.validate_credentials("seedance-2-0-260128", credentials())

    assert requests == [
        CapturedRequest(
            method="GET",
            path="contents/generations/tasks?page_num=1&page_size=1",
        )
    ]


def test_seedream_validate_credentials_uses_image_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        raise ArkHTTPError(405, "method not allowed")

    monkeypatch.setattr(model, "request_model", fake_request_model)

    model.validate_credentials("seedream-5-0-260128", credentials())

    assert requests == [CapturedRequest(method="GET", path="images/generations")]


def test_polling_validate_credentials_rejects_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()

    def fake_request_model(**_: Any) -> Any:
        raise ArkHTTPError(401, "unauthorized")

    monkeypatch.setattr(model, "request_model", fake_request_model)

    with pytest.raises(CredentialsValidateFailedError):
        model.validate_credentials("seedream-5-0-260128", credentials())


def test_live_credentials_validation() -> None:
    api_key = os.getenv("BYTEPLUS_API_KEY")
    if not api_key:
        pytest.skip("BYTEPLUS_API_KEY is not set")

    model = make_model()
    model.validate_credentials(
        "seedance-2-0-260128",
        {
            "ark_api_key": api_key,
            "api_endpoint_host": os.getenv(
                "BYTEPLUS_API_ENDPOINT",
                "https://ark.ap-southeast.bytepluses.com/api/v3",
            ),
        },
    )


def test_seedance_start_polling_creates_task_without_web_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="make a calm ocean video"),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/frame.png",
                    ),
                ],
            )
        ],
        model_parameters={"duration": 5, "resolution": "720p", "web_search": True},
        stream=False,
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.RUNNING
    assert result.plugin_state == {
        "task_id": "task-1",
        "model": "seedance-2-0-260128",
        "platform": "byteplus",
    }
    assert requests[0].method == "POST"
    assert requests[0].path == "contents/generations/tasks"
    assert requests[0].payload_dict() == {
        "model": "seedance-2-0-260128",
        "content": [
            {"type": "text", "text": "make a calm ocean video"},
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/frame.png"},
                "role": "first_frame",
            },
        ],
        "duration": 5,
        "resolution": "720p",
    }


def test_seedance_start_polling_fails_on_invalid_task_response_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()

    def fake_request_model(**kwargs: Any) -> Any:
        return provider_response(kwargs, {"status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="make a calm ocean video")],
        model_parameters={},
        stream=False,
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error is not None
    assert "Invalid Seedance task response" in result.error


def test_seedance_check_polling_returns_video_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    monkeypatch.setattr(
        model,
        "usage_from_provider_payload",
        lambda **_: LLMUsage.empty_usage(),
    )

    def fake_request_model(**kwargs: Any) -> Any:
        assert kwargs["method"] == "GET"
        assert kwargs["path"] == "contents/generations/tasks/task-1"
        return provider_response(
            kwargs,
            {
                "id": "task-1",
                "status": "succeeded",
                "content": {"video_url": "https://example.com/result.mp4"},
                "usage": {"completion_tokens": 12, "total_tokens": 12},
            },
        )

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._check_polling(
        model="seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"task_id": "task-1"},
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.SUCCEEDED
    assert result.result is not None
    assert isinstance(result.result.message.content, list)
    video = result.result.message.content[0]
    assert isinstance(video, VideoPromptMessageContent)
    assert video.url == "https://example.com/result.mp4"
    assert video.mime_type == "video/mp4"


def test_seedance_check_polling_rejects_legacy_state_alias() -> None:
    model = make_model()

    result = model._check_polling(
        model="seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"job_id": "task-1"},
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error is not None
    assert "Invalid Seedance polling state" in result.error


@pytest.mark.parametrize(
    "error", [ArkHTTPError(429, "rate limited"), URLError("timed out")]
)
def test_seedance_check_polling_keeps_running_on_retryable_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    model = make_model()

    def fake_request_model(**_: Any) -> Any:
        raise error

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._check_polling(
        model="seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"task_id": "task-1"},
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.RUNNING
    assert result.plugin_state == {"task_id": "task-1"}
    assert result.next_check_after_seconds == 10


def test_seedance_15_rejects_video_input() -> None:
    model = make_model()

    with pytest.raises(InvokeError, match="video and audio input is only supported"):
        model._start_polling(
            model="seedance-1-5-pro-251215",
            credentials=credentials(),
            prompt_messages=[
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="make a video"),
                        VideoPromptMessageContent(
                            format="mp4",
                            mime_type="video/mp4",
                            url="https://example.com/input.mp4",
                        ),
                    ],
                )
            ],
            model_parameters={},
            stream=False,
            workflow_run_id="wr-1",
            node_id="llm-1",
        )


def test_seedance_2_accepts_reference_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="animate this scene with music"),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/reference.png",
                    ),
                    AudioPromptMessageContent(
                        format="mp3",
                        mime_type="audio/mpeg",
                        url="https://example.com/reference.mp3",
                    ),
                ],
            )
        ],
        model_parameters={},
        stream=False,
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.RUNNING
    payload = requests[0].payload_dict()
    assert payload["content"][1]["role"] == "reference_image"
    assert payload["content"][2]["role"] == "reference_audio"


def test_seedream_start_polling_returns_b64_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []
    monkeypatch.setattr(
        model,
        "usage_from_provider_payload",
        lambda **_: LLMUsage.empty_usage(),
    )

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(
            kwargs,
            {
                "model": "seedream-5-0-260128",
                "data": [{"b64_json": "aW1hZ2U="}],
            },
        )

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="seedream-5-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="draw a small cabin")],
        model_parameters={
            "response_format": "b64_json",
            "output_format": "png",
            "max_images": 3,
            "web_search": True,
        },
        stream=False,
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.SUCCEEDED
    payload = requests[0].payload_dict()
    assert payload["model"] == "seedream-5-0-260128"
    assert "tools" not in payload
    assert payload["sequential_image_generation_options"] == {"max_images": 3}
    assert result.result is not None
    assert isinstance(result.result.message.content, list)
    image = result.result.message.content[0]
    assert isinstance(image, ImagePromptMessageContent)
    assert image.base64_data == "aW1hZ2U="
    assert image.mime_type == "image/png"


@pytest.mark.parametrize(
    ("response", "expected_error"),
    [
        (
            {
                "error": {
                    "code": "SensitiveContentDetected",
                    "message": "content rejected",
                }
            },
            "SensitiveContentDetected: content rejected",
        ),
        (
            {
                "data": [
                    {
                        "error": {
                            "code": "ImageFailed",
                            "message": "one image failed",
                        }
                    }
                ]
            },
            "ImageFailed: one image failed",
        ),
    ],
)
def test_seedream_start_polling_failed_responses(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
    expected_error: str,
) -> None:
    model = make_model()

    def fake_request_model(**kwargs: Any) -> Any:
        return provider_response(kwargs, response)

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="seedream-5-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="draw a cabin")],
        model_parameters={},
        stream=False,
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error == expected_error


@pytest.mark.parametrize(
    ("task_payload", "expected_error"),
    [
        (
            {
                "id": "task-1",
                "status": "failed",
                "error": {"code": "TaskFailed", "message": "provider failed"},
            },
            "TaskFailed: provider failed",
        ),
        ({"id": "task-1", "status": "mystery"}, "unknown task status"),
        (
            {"id": "task-1", "status": "succeeded", "content": {}},
            "without video_url",
        ),
    ],
)
def test_seedance_check_polling_failed_terminal_states(
    monkeypatch: pytest.MonkeyPatch,
    task_payload: dict[str, Any],
    expected_error: str,
) -> None:
    model = make_model()

    def fake_request_model(**kwargs: Any) -> Any:
        return provider_response(kwargs, task_payload)

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._check_polling(
        model="seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"task_id": "task-1"},
        workflow_run_id="wr-1",
        node_id="llm-1",
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error is not None
    assert expected_error in result.error


def test_plugin_registration_loads_byteplus_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(plugin_root)

    registration = PluginRegistration(DifyPluginEnv())

    assert "byteplus" in registration.models_mapping
    assert "volcengine" not in registration.models_mapping

    models = {
        model.model
        for model in registration.models_mapping["byteplus"][0].models
        if model.model_type == ModelType.LLM
    }

    assert "seedance-2-0-260128" in models
    assert "doubao-seedance-2-0-260128" not in models
