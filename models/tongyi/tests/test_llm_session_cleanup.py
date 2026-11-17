import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
import yaml
from dashscope.api_entities.dashscope_response import (
    GenerationOutput,
    GenerationResponse,
    GenerationUsage,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.message import ImagePromptMessageContent, UserPromptMessage
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
)

from models.llm.llm import TongyiLargeLanguageModel


def _model(vision: bool = False) -> TongyiLargeLanguageModel:
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    model.get_model_mode = MagicMock(return_value="chat")
    features = [ModelFeature.VISION] if vision else []
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=features)
    )
    model._handle_generate_response = MagicMock(return_value="result")
    return model


def _generate(model: TongyiLargeLanguageModel, stream: bool = False):
    return model._generate(*_invoke_args(), stream=stream)


def _invoke_args():
    return (
        "qwen-plus",
        {"dashscope_api_key": "test-key"},
        [UserPromptMessage(content="hello")],
        {},
    )


@contextmanager
def _sdk_call(*, session=None, sessions=None, vision=False, error=None):
    factory_options = {"side_effect": sessions} if sessions else {"return_value": session}
    target = (
        "models.llm.llm.MultiModalConversation.call"
        if vision
        else "models.llm.llm.Generation.call"
    )
    call_options = {"return_value": MagicMock()}
    if error is not None:
        call_options["side_effect"] = error
    with patch("models.llm.llm.requests.Session", **factory_options), patch(
        target, **call_options
    ) as call:
        yield call


@pytest.fixture
def session():
    return MagicMock()


@pytest.mark.parametrize("vision", [False, True])
def test_generate_passes_session_to_text_and_vision_calls(vision: bool, session) -> None:
    model = _model(vision)
    with _sdk_call(session=session, vision=vision) as call:
        assert _generate(model) == "result"
    assert call.call_args.kwargs["session"] is session
    session.close.assert_called_once_with()


def test_each_generate_call_gets_an_isolated_session() -> None:
    model = _model()
    first, second = MagicMock(), MagicMock()
    with _sdk_call(sessions=[first, second]) as call:
        _generate(model)
        _generate(model)
    assert [item.kwargs["session"] for item in call.call_args_list] == [first, second]
    first.close.assert_called_once_with()
    second.close.assert_called_once_with()


@contextmanager
def _stream_call(underlying, session):
    model = _model()
    model._handle_generate_stream_response = MagicMock(return_value=underlying)
    with _sdk_call(session=session):
        yield model


def _public_stream(model: TongyiLargeLanguageModel):
    model._validate_and_filter_model_parameters = MagicMock(return_value={})
    return model.invoke(*_invoke_args(), stream=True)


@pytest.mark.parametrize("outcome", ["exhaust", "close", "error"])
def test_stream_closes_session_for_all_exit_paths(outcome, session) -> None:
    def underlying():
        yield "chunk"
        if outcome == "error":
            raise RuntimeError("broken stream")

    with _stream_call(underlying(), session) as model:
        stream = _public_stream(model)
        if outcome == "exhaust":
            assert list(stream) == ["chunk"]
        elif outcome == "close":
            assert next(stream) == "chunk"
            stream.close()
        else:
            with pytest.raises(RuntimeError, match="broken stream"):
                list(stream)
    session.close.assert_called_once_with()


def test_stream_result_remains_generator_compatible(session) -> None:
    with _stream_call(iter(["chunk"]), session) as model:
        result = _generate(model, stream=True)
        assert isinstance(result, Generator)
        assert list(result) == ["chunk"]
    session.close.assert_called_once_with()


@pytest.mark.parametrize(
    "error_type",
    [
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ReadTimeout,
    ],
)
def test_requests_errors_transform_to_connection_error(error_type) -> None:
    error = error_type("request failed")
    assert isinstance(_model()._transform_invoke_error(error), InvokeConnectionError)


def test_nonstream_handler_error_closes_session(session) -> None:
    model = _model()
    model._handle_generate_response.side_effect = RuntimeError("invalid response")
    with _sdk_call(session=session), pytest.raises(RuntimeError, match="invalid response"):
        _generate(model)
    session.close.assert_called_once_with()


def test_nonstream_read_timeout_is_not_replayed_and_closes_session(session) -> None:
    model = _model()
    with _sdk_call(
        session=session, error=requests.exceptions.ReadTimeout("timeout")
    ) as call:
        with pytest.raises(requests.exceptions.ReadTimeout):
            _generate(model)
    call.assert_called_once()
    session.close.assert_called_once_with()


@pytest.fixture
def media_request(monkeypatch, tmp_path, session):
    name = "qwen3.8-flash"
    schema_path = (
        Path(__file__).resolve().parents[1] / "models" / "llm" / f"{name}.yaml"
    )
    schema = AIModelEntity.model_validate(yaml.safe_load(schema_path.read_text()))
    model = TongyiLargeLanguageModel(model_schemas=[schema])
    messages = [
        UserPromptMessage(
            content=[
                ImagePromptMessageContent(
                    format="png", mime_type="image/png", base64_data="cGl4ZWxz"
                )
            ]
        )
    ]
    monkeypatch.setattr("models.llm.llm.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("models.llm.llm.requests.Session", lambda: session)
    return model, (
        name,
        {"dashscope_api_key": "test-key"},
        messages,
        {"enable_thinking": False},
    )


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "failure_type", [requests.exceptions.ConnectionError, BaseException]
)
def test_media_preprocessing_failure_removes_files(
    media_request, tmp_path, session, stream, failure_type
):
    model, args = media_request
    failure = failure_type("media request failed")

    def fail_upload(*args, **kwargs):
        assert len(model._temp_files) == 1
        assert Path(model._temp_files[0]).read_bytes() == b"pixels"
        raise failure

    expected_error = (
        InvokeConnectionError if isinstance(failure, Exception) else BaseException
    )
    with (
        patch(
            "models.llm.llm.MultiModalConversation._preprocess_messages",
            side_effect=fail_upload,
        ),
        pytest.raises(expected_error, match="media request failed") as caught,
    ):
        list(model.invoke(*args, stream=stream))
    if not isinstance(failure, Exception):
        assert caught.value is failure
    assert list(tmp_path.iterdir()) == []
    assert model._temp_files == []
    session.close.assert_called_once_with()


def test_media_conversion_failure_removes_preceding_files(
    media_request, tmp_path, session
):
    model, args = media_request
    args[2][0].content.append(
        ImagePromptMessageContent(format="png", mime_type="image/png", base64_data="a")
    )
    with (
        patch("models.llm.llm.MultiModalConversation.call") as call,
        pytest.raises(InvokeError, match="base64"),
    ):
        list(model.invoke(*args, stream=False))
    call.assert_not_called()
    assert list(tmp_path.iterdir()) == []
    assert model._temp_files == []
    session.close.assert_called_once_with()


def test_media_partial_write_failure_removes_file(
    media_request, tmp_path, session, monkeypatch
):
    model, args = media_request
    write_bytes = Path.write_bytes
    failure = OSError("disk full after partial write")

    def partial_write(path, data):
        write_bytes(path, data[:1])
        raise failure

    monkeypatch.setattr(Path, "write_bytes", partial_write)
    with pytest.raises(OSError) as caught:
        model._generate(*args, stream=False)
    assert caught.value is failure
    assert list(tmp_path.iterdir()) == []
    assert model._temp_files == []
    session.close.assert_called_once_with()


@pytest.mark.parametrize(
    "outcome", ["response", "response_error", "stream", "stream_error", "close"]
)
def test_media_files_live_until_response_finishes(
    media_request, tmp_path, session, outcome
):
    model, args = media_request
    stream = outcome in {"stream", "stream_error", "close"}

    def response(content, finish_reason=None):
        return GenerationResponse(
            status_code=200,
            output=GenerationOutput(
                choices=[
                    {
                        "message": {
                            "role": "assistant",
                            "content": [{"text": content}] if content else "",
                        },
                        "finish_reason": finish_reason,
                    }
                ]
            ),
            usage=GenerationUsage(input_tokens=1, output_tokens=1),
        )

    def streamed_response():
        yield response("hello")
        if outcome == "stream_error":
            raise RuntimeError("broken stream")
        yield response("", "stop")

    def call(**kwargs):
        assert len(model._temp_files) == 1
        assert Path(model._temp_files[0]).read_bytes() == b"pixels"
        if stream:
            return streamed_response()
        if outcome == "response_error":
            return GenerationResponse(
                status_code=400, message="bad response", request_id="cleanup-request"
            )
        return response("hello", "stop")

    with patch("models.llm.llm.MultiModalConversation.call", side_effect=call):
        result = model.invoke(*args, stream=stream)
        if stream:
            assert next(result).delta.message.content == "hello"
            assert len(list(tmp_path.iterdir())) == 1
            session.close.assert_not_called()
            if outcome == "stream_error":
                with pytest.raises(RuntimeError, match="broken stream"):
                    list(result)
            elif outcome == "close":
                result.close()
            else:
                list(result)
        elif outcome == "response_error":
            with pytest.raises(InvokeBadRequestError, match="cleanup-request"):
                list(result)
        else:
            chunks = list(result)
            assert len(chunks) == 1
            assert chunks[0].delta.message.content == "hello"
    assert list(tmp_path.iterdir()) == []
    assert model._temp_files == []
    session.close.assert_called_once_with()
