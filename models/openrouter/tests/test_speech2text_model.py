import base64
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.speech2text import speech2text

STT_DIR = Path(__file__).resolve().parent.parent / "models" / "speech2text"
MODEL = "openai/whisper-large-v3-turbo"


def load_schemas() -> list[AIModelEntity]:
    return [
        AIModelEntity.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(STT_DIR.glob("*.yaml"))
        if not path.name.startswith("_")
    ]


def json_response(payload: dict, status_code: int = 200) -> Mock:
    response = Mock()
    response.ok = 200 <= status_code < 300
    response.status_code = status_code
    response.json.return_value = payload
    return response


class TestSpeech2TextSchemas(unittest.TestCase):
    def test_position_list_matches_shipped_schemas(self) -> None:
        positions = yaml.safe_load((STT_DIR / "_position.yaml").read_text(encoding="utf-8"))
        schemas = load_schemas()
        self.assertEqual(sorted(positions), sorted(schema.model for schema in schemas))
        self.assertTrue(all(schema.model_type == ModelType.SPEECH2TEXT for schema in schemas))


class TestDetectAudioFormat(unittest.TestCase):
    def test_known_containers(self) -> None:
        cases = {
            b"RIFF\x00\x00\x00\x00WAVEfmt ": "wav",
            b"fLaC\x00\x00\x00\x22": "flac",
            b"OggS\x00\x02\x00\x00": "ogg",
            b"\x00\x00\x00\x20ftypM4A \x00\x00": "m4a",
            b"\x00\x00\x00\x18ftypmp42\x00\x00": "m4a",
            b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81": "webm",
            b"\xff\xf1\x50\x80\x02\x1f\xfc": "aac",
            b"ID3\x04\x00\x00\x00\x00": "mp3",
            b"\xff\xfb\x90\x64\x00": "mp3",
        }
        for header, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(speech2text.detect_audio_format(header), expected)


class TestOpenRouterSpeech2TextModel(unittest.TestCase):
    def setUp(self) -> None:
        self.stt = speech2text.OpenRouterSpeech2TextModel(model_schemas=load_schemas())

    @patch("models._audio_utils.requests.post")
    def test_invoke_sends_base64_audio_and_returns_text(self, mock_post: Mock) -> None:
        mock_post.return_value = json_response({"text": "Hello world", "usage": {"seconds": 1}})
        audio = b"RIFF\x24\x00\x00\x00WAVEfmt data"

        text = self.stt._invoke(
            model=MODEL, credentials={"api_key": "test-key"}, file=io.BytesIO(audio)
        )

        self.assertEqual(text, "Hello world")
        mock_post.assert_called_once_with(
            "https://openrouter.ai/api/v1/audio/transcriptions",
            timeout=(10, 300),
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://dify.ai/",
                "X-Title": "Dify",
            },
            json={
                "model": MODEL,
                "input_audio": {"data": base64.b64encode(audio).decode(), "format": "wav"},
            },
        )

    @patch("models._audio_utils.requests.post")
    def test_custom_endpoint_is_normalized(self, mock_post: Mock) -> None:
        mock_post.return_value = json_response({"text": ""})

        self.stt._invoke(
            model=MODEL,
            credentials={"api_key": "k", "endpoint_url": "https://proxy.example.com/v1/ "},
            file=io.BytesIO(b"ID3audio"),
        )

        self.assertEqual(
            mock_post.call_args.args[0], "https://proxy.example.com/v1/audio/transcriptions"
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["input_audio"]["format"], "mp3")

    def test_empty_file_is_rejected_without_calling_api(self) -> None:
        with patch("models._audio_utils.requests.post") as mock_post:
            with self.assertRaises(InvokeBadRequestError):
                self.stt._invoke(model=MODEL, credentials={"api_key": "k"}, file=io.BytesIO())
            mock_post.assert_not_called()

    @patch("models._audio_utils.requests.post")
    def test_invalid_response_is_server_error(self, mock_post: Mock) -> None:
        for payload in ({"unexpected": True}, {"text": None}):
            with self.subTest(payload=payload):
                mock_post.return_value = json_response(payload)
                with self.assertRaises(InvokeServerUnavailableError):
                    self.stt._invoke(
                        model=MODEL, credentials={"api_key": "k"}, file=io.BytesIO(b"ID3")
                    )

    @patch("models._audio_utils.requests.post")
    def test_http_errors_map_to_dify_errors(self, mock_post: Mock) -> None:
        cases = [
            (400, InvokeBadRequestError),
            (403, InvokeAuthorizationError),
            (413, InvokeBadRequestError),
            (429, InvokeRateLimitError),
            (503, InvokeServerUnavailableError),
        ]
        for status_code, expected_error in cases:
            with self.subTest(status_code=status_code):
                mock_post.return_value = json_response(
                    {"error": {"message": "Audio too long", "code": status_code}}, status_code
                )
                with self.assertRaises(expected_error) as ctx:
                    self.stt.invoke(
                        model=MODEL, credentials={"api_key": "k"}, file=io.BytesIO(b"ID3")
                    )
                self.assertIn("Audio too long", str(ctx.exception))

    @patch("models._audio_utils.requests.post")
    def test_timeout_is_connection_error(self, mock_post: Mock) -> None:
        mock_post.side_effect = requests.exceptions.Timeout()
        with self.assertRaises(InvokeConnectionError):
            self.stt.invoke(model=MODEL, credentials={"api_key": "k"}, file=io.BytesIO(b"ID3"))

    @patch("models._audio_utils.requests.post")
    def test_validate_credentials_sends_sdk_demo_file(self, mock_post: Mock) -> None:
        mock_post.return_value = json_response({"text": "demo"})

        self.stt.validate_credentials(model=MODEL, credentials={"api_key": "k"})

        input_audio = mock_post.call_args.kwargs["json"]["input_audio"]
        self.assertEqual(input_audio["format"], "mp3")
        self.assertTrue(input_audio["data"])

    @patch("models._audio_utils.requests.post")
    def test_validate_credentials_wraps_failures(self, mock_post: Mock) -> None:
        mock_post.return_value = json_response({"error": {"message": "No auth"}}, 401)
        with self.assertRaises(CredentialsValidateFailedError):
            self.stt.validate_credentials(model=MODEL, credentials={"api_key": "bad"})


if __name__ == "__main__":
    unittest.main()
