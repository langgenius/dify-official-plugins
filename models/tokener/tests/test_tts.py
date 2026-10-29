import json
from unittest.mock import patch

import pytest
import requests
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelPropertyKey, ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

MODELS = ["tts-1", "tts-1-hd"]


def tts_model():
    import yaml
    from dify_plugin.entities.model import AIModelEntity
    from test_tts_catalog import catalog

    from scripts.sync_catalog import render_catalog

    model = PluginRegistration(DifyPluginEnv()).get_model_instance("tokener", ModelType.TTS)
    files = render_catalog(catalog(), model_type="tts")
    model.model_schemas = [
        AIModelEntity.model_validate(yaml.safe_load(content))
        for name, content in files.items()
        if name != "_position.yaml"
    ]
    return model


def response(body=b"audio\x00\xff", status=200):
    result = requests.Response()
    result.status_code = status
    result._content = body
    result._content_consumed = True
    return result


@pytest.mark.parametrize("model_id", MODELS)
def test_tts_fixture_public_invoke_keeps_selected_model_and_audio_bytes(model_id):
    model = tts_model()
    assert {schema.model for schema in model.model_schemas} == set(MODELS)
    credentials = {"api_key": "test", "endpoint_model_name": "wrong", "endpoint_url": "wrong"}
    with patch("requests.sessions.Session.send", return_value=response()) as send:
        result = b"".join(
            model.invoke(model_id, "tenant", credentials, "Hello.", "echo", user="user")
        )
    assert result == b"audio\x00\xff"
    request = send.call_args.args[0]
    assert request.method == "POST"
    assert request.url == "https://api.tokener.ai/v1/audio/speech"
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.body) == {
        "model": model_id,
        "voice": "echo",
        "response_format": "mp3",
        "input": "Hello.",
    }
    assert send.call_count == 1
    assert credentials["endpoint_model_name"] == "wrong"


@pytest.mark.parametrize("voice", ["", "invalid", "catalog-voice"])
def test_tts_voice_and_language_follow_catalog_metadata(voice):
    import yaml
    from dify_plugin.entities.model import AIModelEntity
    from test_tts_catalog import catalog

    from scripts.sync_catalog import render_catalog

    payload = catalog()
    payload["models"][0]["audio"]["voices"] = [
        {"id": "catalog-voice", "languages": ["en-US", "zh-Hans"]},
        {"id": "catalog-default", "languages": ["en-US"]},
    ]
    payload["models"][0]["audio"]["defaultVoice"] = "catalog-default"
    files = render_catalog(payload, model_type="tts")
    model = tts_model()
    model.model_schemas = [AIModelEntity.model_validate(yaml.safe_load(files["tts-1.yaml"]))]
    assert model.get_tts_model_voices("tts-1", {}, "zh-Hans") == [
        {"name": "catalog-voice", "value": "catalog-voice"}
    ]
    assert model.get_tts_model_voices("tts-1", {}, "en-US") == [
        {"name": "catalog-voice", "value": "catalog-voice"},
        {"name": "catalog-default", "value": "catalog-default"},
    ]
    assert model.get_tts_model_voices("tts-1", {}, "en") == []
    with patch("requests.post", return_value=response()) as post:
        list(model.invoke("tts-1", "tenant", {"api_key": "test"}, "hello", voice))
    assert post.call_args.kwargs["json"]["voice"] == (
        "catalog-voice" if voice == "catalog-voice" else "catalog-default"
    )


@pytest.mark.parametrize(
    "model_id,limit,expected",
    [("tts-1", 5, ["abcde", "FGHIJ", "!"]), ("tts-1-hd", 4, ["abcd", "eFGH", "IJ!"])],
)
@pytest.mark.parametrize("audio_format", ["mp3", "aac", "opus", "pcm"])
def test_tts_uses_per_model_limit_and_format_and_streams_in_order(
    model_id, limit, expected, audio_format
):
    model = tts_model()
    for schema in model.model_schemas:
        schema.model_properties[ModelPropertyKey.WORD_LIMIT] = (
            limit if schema.model == model_id else 1
        )
        schema.model_properties[ModelPropertyKey.AUDIO_TYPE] = audio_format
    replies = [response(bytes([i, 255])) for i in range(len(expected))]
    with patch("requests.post", side_effect=replies) as post:
        audio = b"".join(
            model.invoke(model_id, "tenant", {"api_key": "test"}, "abcdeFGHIJ!", "echo")
        )
    assert audio == b"".join(bytes([i, 255]) for i in range(len(expected)))
    assert [call.kwargs["json"] for call in post.call_args_list] == [
        {"model": model_id, "voice": "echo", "response_format": audio_format, "input": chunk}
        for chunk in expected
    ]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("你好世界你好世界", ["你好世界你", "好世界"]),
        ("one. two!  End?", ["one.", "two!", "End", "?"]),
        ("     abcde     fghij", ["abcde", "fghij"]),
    ],
)
def test_tts_splits_unicode_punctuation_and_whitespace_without_empty_requests(text, expected):
    model = tts_model()
    model.model_schemas[0].model_properties[ModelPropertyKey.WORD_LIMIT] = 5
    with patch("requests.post", side_effect=lambda *a, **k: response()) as post:
        list(
            model.invoke(model.model_schemas[0].model, "tenant", {"api_key": "test"}, text, "echo")
        )
    assert [call.kwargs["json"]["input"] for call in post.call_args_list] == expected


@pytest.mark.parametrize(
    "status,error",
    [
        (400, InvokeBadRequestError),
        (401, InvokeAuthorizationError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (503, InvokeServerUnavailableError),
    ],
)
def test_tts_error_closes_response_and_stops_sequence_after_partial_audio(status, error):
    model = tts_model()
    model.model_schemas[0].model_properties[ModelPropertyKey.WORD_LIMIT] = 5
    first, failed = response(b"first"), response(b"private upstream detail", status)
    with (
        patch("requests.post", side_effect=[first, failed]) as post,
        patch.object(first, "close", wraps=first.close) as close_first,
        patch.object(failed, "close", wraps=failed.close) as close_failed,
        pytest.raises(error) as caught,
    ):
        stream = model.invoke(
            model.model_schemas[0].model, "tenant", {"api_key": "test"}, "abcdeFGHIJrest", "echo"
        )
        assert next(stream) == b"first"
        next(stream)
    assert post.call_count == 2
    close_first.assert_called_once()
    close_failed.assert_called_once()
    assert "private upstream detail" not in str(caught.value)


def test_tts_network_failure_does_not_retry_or_leak_details():
    with (
        patch("requests.post", side_effect=requests.Timeout("private detail")) as post,
        pytest.raises(InvokeConnectionError) as caught,
    ):
        list(tts_model().invoke("tts-1", "tenant", {"api_key": "test"}, "hello", "echo"))
    assert post.call_count == 1
    assert "private detail" not in str(caught.value)


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_tts_empty_text_does_not_send_request(text):
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError):
        list(tts_model().invoke("tts-1", "tenant", {"api_key": "test"}, text, "echo"))
    post.assert_not_called()


def test_tts_no_audio_is_an_error_and_success_closes_response():
    reply = response(b"")
    with (
        patch("requests.post", return_value=reply),
        patch.object(reply, "close", wraps=reply.close) as close,
        pytest.raises(InvokeBadRequestError),
    ):
        list(tts_model().invoke("tts-1", "tenant", {"api_key": "test"}, "hello", "echo"))
    close.assert_called_once()


def test_tts_excluded_model_cannot_be_invoked():
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError):
        list(
            tts_model().invoke(
                "gpt-4o-mini-tts-2025-12-15", "tenant", {"api_key": "test"}, "hello", "echo"
            )
        )
    post.assert_not_called()


def test_tts_credential_validation_uses_default_voice_and_transforms_errors():
    with patch("requests.post", return_value=response()) as post:
        tts_model().validate_credentials("tts-1", {"api_key": "test"})
    assert post.call_args.kwargs["json"] == {
        "model": "tts-1",
        "voice": "alloy",
        "input": "Hello Dify!",
        "response_format": "mp3",
    }
    with (
        patch("requests.post", return_value=response(b"private", 403)),
        pytest.raises(CredentialsValidateFailedError),
    ):
        tts_model().validate_credentials("tts-1-hd", {"api_key": "test"})


def test_tts_stream_yields_first_segment_before_requesting_second():
    model = tts_model()
    model.model_schemas[0].model_properties[ModelPropertyKey.WORD_LIMIT] = 5
    first, second = response(b"first"), response(b"second")
    with (
        patch("requests.post", side_effect=[first, second]) as post,
        patch.object(first, "close", wraps=first.close) as close_first,
        patch.object(second, "close", wraps=second.close) as close_second,
    ):
        stream = model.invoke(
            model.model_schemas[0].model, "tenant", {"api_key": "test"}, "abcdeFGHIJ", "echo"
        )
        assert next(stream) == b"first"
        assert post.call_count == 1
        assert post.call_args.kwargs["stream"] is True
        assert next(stream) == b"second"
        assert post.call_count == 2
        with pytest.raises(StopIteration):
            next(stream)
    close_first.assert_called_once()
    close_second.assert_called_once()


def test_tts_stream_read_failure_closes_response_after_partial_audio():
    def chunks():
        yield b"first"
        raise requests.ConnectionError("private detail")

    reply = response()
    with (
        patch("requests.post", return_value=reply),
        patch.object(reply, "iter_content", return_value=chunks()),
        patch.object(reply, "close", wraps=reply.close) as close,
    ):
        stream = tts_model().invoke("tts-1", "tenant", {"api_key": "test"}, "hello", "echo")
        assert next(stream) == b"first"
        with pytest.raises(InvokeConnectionError) as caught:
            next(stream)
    close.assert_called_once()
    assert "private detail" not in str(caught.value)


def test_tts_stream_close_releases_in_flight_response():
    reply = response(b"audio" * 1024)
    with (
        patch("requests.post", return_value=reply),
        patch.object(reply, "close", wraps=reply.close) as close,
    ):
        stream = tts_model().invoke("tts-1", "tenant", {"api_key": "test"}, "hello", "echo")
        assert len(next(stream)) == 1024
        stream.close()
    close.assert_called_once()


@pytest.mark.parametrize("audio_format", ["wav", "flac"])
def test_tts_runtime_rejects_unsafe_audio_format_before_request(audio_format):
    model = tts_model()
    model.model_schemas[0].model_properties[ModelPropertyKey.AUDIO_TYPE] = audio_format
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError):
        list(
            model.invoke(
                model.model_schemas[0].model, "tenant", {"api_key": "test"}, "hello", "echo"
            )
        )
    post.assert_not_called()


def test_tts_all_empty_segments_raise_and_each_response_is_closed():
    model = tts_model()
    model.model_schemas[0].model_properties[ModelPropertyKey.WORD_LIMIT] = 5
    replies = [response(b"") for _ in range(3)]
    with (
        patch("requests.post", side_effect=replies) as post,
        patch.object(replies[0], "close", wraps=replies[0].close) as first_close,
        patch.object(replies[1], "close", wraps=replies[1].close) as second_close,
        patch.object(replies[2], "close", wraps=replies[2].close) as third_close,
        pytest.raises(InvokeBadRequestError),
    ):
        list(
            model.invoke(
                model.model_schemas[0].model,
                "tenant",
                {"api_key": "test"},
                "abcdeFGHIJrest",
                "echo",
            )
        )
    assert post.call_count == 3
    first_close.assert_called_once()
    second_close.assert_called_once()
    third_close.assert_called_once()
