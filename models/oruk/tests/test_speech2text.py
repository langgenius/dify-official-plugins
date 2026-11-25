"""Offline unit tests for OrukSpeech2TextModel."""

import io
from unittest.mock import patch

import httpx
import pytest
from dify_plugin.entities.model import FetchFrom, ModelPropertyKey, ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models.speech2text.speech2text import (
    DEFAULT_ENDPOINT_URL,
    MAX_AUDIO_BYTES,
    OrukSpeech2TextModel,
    detect_audio_upload_meta,
    is_hosted_oruk_endpoint,
    normalize_endpoint_url,
)


def _model() -> OrukSpeech2TextModel:
    return object.__new__(OrukSpeech2TextModel)


def _json_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("POST", f"{DEFAULT_ENDPOINT_URL}/audio/transcriptions"),
    )


class TestEndpointNormalization:
    def test_defaults_when_blank(self):
        assert normalize_endpoint_url(None) == DEFAULT_ENDPOINT_URL
        assert normalize_endpoint_url("") == DEFAULT_ENDPOINT_URL
        assert normalize_endpoint_url("   ") == DEFAULT_ENDPOINT_URL

    def test_normalizes_root_v1_and_full_path(self):
        assert normalize_endpoint_url("https://speech-api.oruk.ai") == DEFAULT_ENDPOINT_URL
        assert normalize_endpoint_url("https://speech-api.oruk.ai/") == DEFAULT_ENDPOINT_URL
        assert normalize_endpoint_url("https://speech-api.oruk.ai/v1/") == DEFAULT_ENDPOINT_URL
        assert (
            normalize_endpoint_url("https://speech-api.oruk.ai/v1/audio/transcriptions")
            == DEFAULT_ENDPOINT_URL
        )
        assert normalize_endpoint_url("http://localhost:8000") == "http://localhost:8000/v1"
        assert normalize_endpoint_url("http://localhost:8000/v1") == "http://localhost:8000/v1"

    def test_rejects_invalid_scheme_or_host(self):
        with pytest.raises(CredentialsValidateFailedError):
            normalize_endpoint_url("ftp://speech-api.oruk.ai/v1")
        with pytest.raises(CredentialsValidateFailedError):
            normalize_endpoint_url("not-a-url")

    def test_identifies_hosted_oruk_endpoints(self):
        assert is_hosted_oruk_endpoint("https://speech-api.oruk.ai/v1") is True
        assert is_hosted_oruk_endpoint("https://oruk.ai/v1") is True
        assert is_hosted_oruk_endpoint("http://localhost:8000/v1") is False
        assert is_hosted_oruk_endpoint("https://notoruk.ai/v1") is False


class TestAudioFormatDetection:
    @pytest.mark.parametrize(
        ("payload", "expected_name", "expected_mime"),
        [
            (b"RIFF\x24\x00\x00\x00WAVEfmt ", "audio.wav", "audio/wav"),
            (b"fLaC\x00\x00\x00\x22", "audio.flac", "audio/flac"),
            (b"OggS\x00\x02\x00\x00", "audio.ogg", "audio/ogg"),
            (b"\x00\x00\x00\x20ftypM4A ", "audio.m4a", "audio/mp4"),
            (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81", "audio.webm", "audio/webm"),
            (b"ID3\x04\x00\x00\x00", "audio.mp3", "audio/mpeg"),
        ],
    )
    def test_detects_anonymous_audio_from_magic_bytes(
        self, payload: bytes, expected_name: str, expected_mime: str
    ):
        assert detect_audio_upload_meta(payload) == (expected_name, expected_mime)

    def test_uses_known_filename_extension_when_present(self):
        assert detect_audio_upload_meta(b"\x00\x01\x02", file_name="/tmp/clip.WAV") == (
            "clip.WAV",
            "audio/wav",
        )


class TestCredentialValidation:
    def test_hosted_endpoint_requires_api_key(self):
        model = _model()
        with pytest.raises(CredentialsValidateFailedError, match="API key is required"):
            model.validate_credentials("oruk-fourier-2b", {"endpoint_url": ""})

    def test_hosted_endpoint_succeeds_on_models_200(self):
        model = _model()
        resp = httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "oruk-fourier-2b"}]},
            request=httpx.Request("GET", f"{DEFAULT_ENDPOINT_URL}/models"),
        )
        with patch("models.speech2text.speech2text.httpx.get", return_value=resp) as mock_get:
            model.validate_credentials("oruk-fourier-2b", {"api_key": "oruk-valid-key"})

        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == f"{DEFAULT_ENDPOINT_URL}/models"
        assert kwargs["headers"]["Authorization"] == "Bearer oruk-valid-key"

    def test_hosted_endpoint_rejects_401(self):
        model = _model()
        resp = httpx.Response(
            401,
            json={"error": {"code": "invalid_api_key", "message": "Invalid or missing API key."}},
            request=httpx.Request("GET", f"{DEFAULT_ENDPOINT_URL}/models"),
        )
        with (
            patch("models.speech2text.speech2text.httpx.get", return_value=resp),
            pytest.raises(CredentialsValidateFailedError, match="invalid_api_key"),
        ):
            model.validate_credentials("oruk-fourier-2b", {"api_key": "bad-key"})

    def test_custom_self_hosted_allows_empty_key_and_404_models_fallback(self):
        model = _model()
        resp_models = httpx.Response(
            404,
            json={"detail": "Not Found"},
            request=httpx.Request("GET", "http://127.0.0.1:8000/v1/models"),
        )
        resp_root = httpx.Response(
            200,
            text="ok",
            request=httpx.Request("GET", "http://127.0.0.1:8000"),
        )
        with patch(
            "models.speech2text.speech2text.httpx.get", side_effect=[resp_models, resp_root]
        ) as mock_get:
            model.validate_credentials(
                "oruk-fourier-2b", {"endpoint_url": "http://127.0.0.1:8000", "api_key": ""}
            )
        assert mock_get.call_count == 2
        assert "Authorization" not in mock_get.call_args_list[0].kwargs["headers"]

    def test_custom_endpoint_network_failure_is_rejected(self):
        model = _model()
        with (
            patch(
                "models.speech2text.speech2text.httpx.get",
                side_effect=httpx.ConnectError("connection refused"),
            ),
            pytest.raises(CredentialsValidateFailedError, match="Could not reach"),
        ):
            model.validate_credentials(
                "oruk-fourier-2b", {"endpoint_url": "http://127.0.0.1:9999"}
            )


class TestSpeech2TextInvoke:
    def test_invoke_success_with_anonymous_wav_stream(self):
        model = _model()
        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
        resp = _json_response(
            200,
            {
                "id": "tr_123",
                "object": "audio.transcription",
                "model": "oruk-fourier-2b",
                "task": "transcription",
                "text": "hello from oruk fourier",
                "language": "en",
                "duration": 1.2,
            },
        )
        with patch("models.speech2text.speech2text.httpx.post", return_value=resp) as mock_post:
            result = model._invoke(
                "oruk-fourier-2b",
                {"api_key": "oruk-key"},
                io.BytesIO(wav_bytes),
            )

        assert result == "hello from oruk fourier"
        args, kwargs = mock_post.call_args
        assert args[0] == f"{DEFAULT_ENDPOINT_URL}/audio/transcriptions"
        assert kwargs["headers"]["Authorization"] == "Bearer oruk-key"
        assert kwargs["data"] == {"model": "oruk-fourier-2b", "response_format": "json"}
        assert kwargs["files"]["file"] == ("audio.wav", wav_bytes, "audio/wav")

    def test_invoke_rejects_empty_and_oversized_audio(self):
        model = _model()
        with pytest.raises(InvokeBadRequestError, match="must not be empty"):
            model._invoke("oruk-fourier-2b", {"api_key": "oruk-key"}, io.BytesIO(b""))

        oversized = io.BytesIO(b"\x00" * (MAX_AUDIO_BYTES + 1))
        with pytest.raises(InvokeBadRequestError, match="30 MiB"):
            model._invoke("oruk-fourier-2b", {"api_key": "oruk-key"}, oversized)

    @pytest.mark.parametrize(
        ("status_code", "expected_exc"),
        [
            (401, InvokeAuthorizationError),
            (403, InvokeAuthorizationError),
            (429, InvokeRateLimitError),
            (400, InvokeBadRequestError),
            (413, InvokeBadRequestError),
            (503, InvokeServerUnavailableError),
        ],
    )
    def test_invoke_maps_http_errors(self, status_code: int, expected_exc: type[Exception]):
        model = _model()
        resp = _json_response(
            status_code,
            {"error": {"code": "err_code", "message": "upstream failure"}},
        )
        with (
            patch("models.speech2text.speech2text.httpx.post", return_value=resp),
            pytest.raises(expected_exc, match="upstream failure"),
        ):
            model._invoke(
                "oruk-fourier-2b",
                {"api_key": "oruk-key"},
                io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt "),
            )

    def test_invoke_maps_timeout_and_malformed_json(self):
        model = _model()
        with (
            patch(
                "models.speech2text.speech2text.httpx.post",
                side_effect=httpx.ReadTimeout("timed out"),
            ),
            pytest.raises(InvokeConnectionError, match="Timed out"),
        ):
            model._invoke(
                "oruk-fourier-2b",
                {"api_key": "oruk-key"},
                io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt "),
            )

        bad_resp = _json_response(200, {"status": "missing_text"})
        with (
            patch("models.speech2text.speech2text.httpx.post", return_value=bad_resp),
            pytest.raises(InvokeServerUnavailableError, match="without a text field"),
        ):
            model._invoke(
                "oruk-fourier-2b",
                {"api_key": "oruk-key"},
                io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt "),
            )

    def test_customizable_model_schema(self):
        model = _model()
        entity = model.get_customizable_model_schema("oruk/orukqwen-asr-1.7b", {})
        assert entity is not None
        assert entity.model == "oruk/orukqwen-asr-1.7b"
        assert entity.fetch_from == FetchFrom.CUSTOMIZABLE_MODEL
        assert entity.model_type == ModelType.SPEECH2TEXT
        assert entity.model_properties[ModelPropertyKey.FILE_UPLOAD_LIMIT] == 30
        assert (
            entity.model_properties[ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS]
            == "flac,mp3,m4a,ogg,wav,webm"
        )
