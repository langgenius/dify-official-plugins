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
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.errors.model import InvokeError

from models.llm import llm as llm_module
from models.llm.llm import (
    VolcengineArkLargeLanguageModel,
    ArkCredentials,
    ArkHTTPError,
    ArkObjectResponse,
    build_chat_completion_request,
    chat_stream_options_from_parameters,
)


def make_model() -> VolcengineArkLargeLanguageModel:
    return VolcengineArkLargeLanguageModel(model_schemas=[])


def credentials() -> dict[str, str]:
    return {
        "ark_api_key": "test-key",
        "api_endpoint_host": "https://ark.example.com/api/v3",
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
        model="doubao-seedance-2-0-260128",
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
        model="doubao-1-5-pro-32k-250115",
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
        "model": "doubao-1-5-pro-32k-250115",
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
        credentials=ArkCredentials(
            ark_api_key="test-key",
            api_endpoint_host="https://ark.cn-beijing.volces.com/api/v3",
        ),
        method="GET",
        path="images/generations",
        response_model=ArkObjectResponse,
        response_context="Invalid test response",
    )

    assert response.model_extra == {"ok": True}
    assert (
        requests[0][0].full_url
        == "https://ark.cn-beijing.volces.com/api/v3/images/generations"
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

    model.validate_credentials("doubao-seedance-2-0-260128", credentials())

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

    model.validate_credentials("doubao-seedream-5-0-260128", credentials())

    assert requests == [CapturedRequest(method="GET", path="images/generations")]


def test_polling_validate_credentials_rejects_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()

    def fake_request_model(**_: Any) -> Any:
        raise ArkHTTPError(401, "unauthorized")

    monkeypatch.setattr(model, "request_model", fake_request_model)

    with pytest.raises(CredentialsValidateFailedError):
        model.validate_credentials("doubao-seedream-5-0-260128", credentials())


def test_seedance_start_polling_creates_task(monkeypatch: pytest.MonkeyPatch) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedance-2-0-260128",
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
        model_parameters={"duration": 5, "resolution": "720p", "max_tokens": 100},
        stream=False,
    )

    assert result.status == LLMPollingStatus.RUNNING
    assert result.plugin_state == {
        "task_id": "task-1",
        "model": "doubao-seedance-2-0-260128",
        "platform": "volcengine",
    }
    assert requests[0].method == "POST"
    assert requests[0].path == "contents/generations/tasks"
    assert requests[0].payload_dict() == {
        "model": "doubao-seedance-2-0-260128",
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
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="make a calm ocean video")],
        model_parameters={},
        stream=False,
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
                "content": {
                    "video_url": "https://example.com/result.mp4",
                },
                "usage": {
                    "completion_tokens": 12,
                    "total_tokens": 12,
                },
            },
        )

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._check_polling(
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"task_id": "task-1"},
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
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"job_id": "task-1"},
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error is not None
    assert "Invalid Seedance polling state" in result.error


def test_seedance_check_polling_keeps_running_on_retryable_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()

    def fake_request_model(**_: Any) -> Any:
        raise ArkHTTPError(429, "rate limited")

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._check_polling(
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"task_id": "task-1"},
    )

    assert result.status == LLMPollingStatus.RUNNING
    assert result.plugin_state == {"task_id": "task-1"}
    assert result.next_check_after_seconds == 10


def test_seedance_check_polling_keeps_running_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()

    def fake_request_model(**_: Any) -> Any:
        raise URLError("timed out")

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._check_polling(
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"task_id": "task-1"},
    )

    assert result.status == LLMPollingStatus.RUNNING
    assert result.plugin_state == {"task_id": "task-1"}
    assert result.next_check_after_seconds == 10


def test_seedance_start_polling_requires_explicit_mode_for_two_images() -> None:
    model = make_model()

    with pytest.raises(
        InvokeError, match="first_frame input_mode requires exactly one image"
    ):
        model._start_polling(
            model="doubao-seedance-2-0-260128",
            credentials=credentials(),
            prompt_messages=[
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="make a video"),
                        ImagePromptMessageContent(
                            format="png",
                            mime_type="image/png",
                            url="https://example.com/a.png",
                        ),
                        ImagePromptMessageContent(
                            format="png",
                            mime_type="image/png",
                            url="https://example.com/b.png",
                        ),
                    ],
                )
            ],
            model_parameters={},
            stream=False,
        )


def test_seedance_start_polling_uses_explicit_first_last_frame_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="make a video"),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/first.png",
                    ),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/last.png",
                    ),
                ],
            )
        ],
        model_parameters={"input_mode": "first_last_frame"},
        stream=False,
    )

    assert result.status == LLMPollingStatus.RUNNING
    payload = requests[0].payload_dict()
    assert payload["content"][1]["role"] == "first_frame"
    assert payload["content"][2]["role"] == "last_frame"
    assert "input_mode" not in payload


def test_seedance_start_polling_uses_reference_image_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="make a video"),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/a.png",
                    ),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/b.png",
                    ),
                ],
            )
        ],
        model_parameters={"input_mode": "reference_image"},
        stream=False,
    )

    assert result.status == LLMPollingStatus.RUNNING
    payload = requests[0].payload_dict()
    assert payload["content"][1]["role"] == "reference_image"
    assert payload["content"][2]["role"] == "reference_image"


def test_seedance_start_polling_uses_reference_images_with_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="extend this scene"),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/reference.png",
                    ),
                    VideoPromptMessageContent(
                        format="mp4",
                        mime_type="video/mp4",
                        url="https://example.com/reference.mp4",
                    ),
                ],
            )
        ],
        model_parameters={},
        stream=False,
    )

    assert result.status == LLMPollingStatus.RUNNING
    payload = requests[0].payload_dict()
    assert payload["content"][1]["role"] == "reference_image"
    assert payload["content"][2]["role"] == "reference_video"


def test_seedance_start_polling_uses_reference_image_with_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedance-2-0-260128",
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
    )

    assert result.status == LLMPollingStatus.RUNNING
    payload = requests[0].payload_dict()
    assert payload["content"][1]["role"] == "reference_image"
    assert payload["content"][2]["role"] == "reference_audio"


def test_volcengine_seedance_web_search_maps_to_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()
    requests: list[CapturedRequest] = []

    def fake_request_model(**kwargs: Any) -> Any:
        requests.append(CapturedRequest.from_kwargs(kwargs))
        return provider_response(kwargs, {"id": "task-1", "status": "queued"})

    monkeypatch.setattr(model, "request_model", fake_request_model)

    model._start_polling(
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="make a timely city video")],
        model_parameters={"web_search": True},
        stream=False,
    )

    assert requests[0].payload_dict()["tools"] == [{"type": "web_search"}]


def test_seedance_start_polling_rejects_frame_role_with_video() -> None:
    model = make_model()

    with pytest.raises(InvokeError, match="cannot be mixed with frame image roles"):
        model._start_polling(
            model="doubao-seedance-2-0-260128",
            credentials=credentials(),
            prompt_messages=[
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="extend this scene"),
                        ImagePromptMessageContent(
                            format="png",
                            mime_type="image/png",
                            url="https://example.com/first.png",
                            opaque_body={"role": "first_frame"},
                        ),
                        VideoPromptMessageContent(
                            format="mp4",
                            mime_type="video/mp4",
                            url="https://example.com/reference.mp4",
                        ),
                    ],
                )
            ],
            model_parameters={},
            stream=False,
        )


def test_seedance_15_rejects_video_input() -> None:
    model = make_model()

    with pytest.raises(InvokeError, match="video and audio input is only supported"):
        model._start_polling(
            model="doubao-seedance-1-5-pro-251215",
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
        )


def test_seedream_start_polling_returns_terminal_image_result(
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
                "model": "doubao-seedream-5-0-260128",
                "data": [
                    {"url": "https://example.com/image.png"},
                ],
                "usage": {
                    "output_tokens": 10,
                    "total_tokens": 10,
                },
            },
        )

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedream-5-0-260128",
        credentials=credentials(),
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="draw a small cabin"),
                    ImagePromptMessageContent(
                        format="png",
                        mime_type="image/png",
                        url="https://example.com/reference.png",
                    ),
                ],
            )
        ],
        model_parameters={"size": "2048x2048", "response_format": "url"},
        stream=False,
    )

    assert result.status == LLMPollingStatus.SUCCEEDED
    assert result.result is not None
    assert isinstance(result.result.message.content, list)
    image = result.result.message.content[0]
    assert isinstance(image, ImagePromptMessageContent)
    assert image.url == "https://example.com/image.png"
    assert requests[0].payload_dict() == {
        "model": "doubao-seedream-5-0-260128",
        "prompt": "draw a small cabin",
        "size": "2048x2048",
        "response_format": "url",
        "image": "https://example.com/reference.png",
    }


def test_volcengine_seedream_web_search_and_max_images_map_to_payload(
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
                "model": "doubao-seedream-5-0-260128",
                "data": [{"url": "https://example.com/image.png"}],
            },
        )

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedream-5-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="draw the latest skyline")],
        model_parameters={
            "sequential_image_generation": "auto",
            "max_images": 3,
            "web_search": True,
        },
        stream=False,
    )

    assert result.status == LLMPollingStatus.SUCCEEDED
    payload = requests[0].payload_dict()
    assert payload["sequential_image_generation"] == "auto"
    assert payload["sequential_image_generation_options"] == {"max_images": 3}
    assert payload["tools"] == [{"type": "web_search"}]


def test_seedream_start_polling_fails_on_response_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()

    def fake_request_model(**kwargs: Any) -> Any:
        return provider_response(
            kwargs,
            {
                "error": {
                    "code": "SensitiveContentDetected",
                    "message": "content rejected",
                }
            },
        )

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedream-5-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="draw a cabin")],
        model_parameters={},
        stream=False,
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error == "SensitiveContentDetected: content rejected"


def test_seedream_start_polling_fails_when_all_images_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = make_model()

    def fake_request_model(**kwargs: Any) -> Any:
        return provider_response(
            kwargs,
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
        )

    monkeypatch.setattr(model, "request_model", fake_request_model)

    result = model._start_polling(
        model="doubao-seedream-5-0-260128",
        credentials=credentials(),
        prompt_messages=[UserPromptMessage(content="draw a cabin")],
        model_parameters={},
        stream=False,
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error == "ImageFailed: one image failed"


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
        model="doubao-seedance-2-0-260128",
        credentials=credentials(),
        plugin_state={"task_id": "task-1"},
    )

    assert result.status == LLMPollingStatus.FAILED
    assert result.error is not None
    assert expected_error in result.error


def test_plugin_registration_loads_volcengine_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(plugin_root)

    registration = PluginRegistration(DifyPluginEnv())

    assert "volcengine" in registration.models_mapping
    assert "byteplus" not in registration.models_mapping

    volcengine_models = {
        model.model
        for model in registration.models_mapping["volcengine"][0].models
        if model.model_type == ModelType.LLM
    }

    assert "doubao-seedance-2-0-260128" in volcengine_models
    assert "seedance-2-0-260128" not in volcengine_models
