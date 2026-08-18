import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import InvokeConnectionError

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
