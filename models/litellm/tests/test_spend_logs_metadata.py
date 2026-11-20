import json
from unittest.mock import Mock, patch

import pytest
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import CredentialsValidateFailedError

from models.llm.llm import (
    SPEND_LOGS_METADATA_HEADER,
    LiteLLMLargeLanguageModel,
    build_spend_logs_metadata,
)

RESPONSE_PAYLOAD = {
    "id": "chatcmpl-test",
    "model": "gpt-6-luna",
    "object": "chat.completion",
    "choices": [{"message": {"role": "assistant", "content": "Hi there"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

POST = "dify_plugin.interfaces.model.openai_compatible.llm.requests.post"


def _response() -> Mock:
    response = Mock()
    response.status_code = 200
    response.encoding = "utf-8"
    response.json.return_value = RESPONSE_PAYLOAD
    return response


def _invoke(*, user: str | None = "user-123", app_id: str | None = None, **credentials):
    model = LiteLLMLargeLanguageModel(model_schemas=[])
    with (
        patch(POST, return_value=_response()) as post,
        patch("models.llm.llm._current_app_id", return_value=app_id),
    ):
        model._invoke(
            model="gpt-6-luna",
            credentials={"mode": "chat", "endpoint_url": "http://localhost:4000", **credentials},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters={},
            stream=False,
            user=user,
        )
    return post.call_args.kwargs["headers"]


def test_disabled_by_default() -> None:
    headers = _invoke()

    assert SPEND_LOGS_METADATA_HEADER not in headers


def test_user_and_app_ids_are_sent() -> None:
    headers = _invoke(enable_spend_logs_metadata="enabled", app_id="app-456")

    assert json.loads(headers[SPEND_LOGS_METADATA_HEADER]) == {
        "dify_sys_user_id": "user-123",
        "dify_sys_app_id": "app-456",
    }


def test_extra_metadata_is_merged() -> None:
    headers = _invoke(
        enable_spend_logs_metadata="enabled",
        spend_logs_metadata='{"team":"growth","env":"prod"}',
    )

    assert json.loads(headers[SPEND_LOGS_METADATA_HEADER]) == {
        "dify_sys_user_id": "user-123",
        "team": "growth",
        "env": "prod",
    }


def test_no_header_without_any_metadata() -> None:
    headers = _invoke(enable_spend_logs_metadata="enabled", user=None, app_id=None)

    assert SPEND_LOGS_METADATA_HEADER not in headers


def test_invalid_json_is_rejected_when_saving_the_model() -> None:
    model = LiteLLMLargeLanguageModel(model_schemas=[])

    with pytest.raises(CredentialsValidateFailedError):
        model.validate_credentials(
            "gpt-6-luna",
            {
                "mode": "chat",
                "endpoint_url": "http://localhost:4000",
                "spend_logs_metadata": "{not json",
            },
        )


def test_non_object_json_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        build_spend_logs_metadata({"spend_logs_metadata": "[1, 2, 3]"}, user=None)
