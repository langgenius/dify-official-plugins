import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import requests
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey, ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.tts.tts import OpenRouterText2SpeechModel

TTS_DIR = Path(__file__).resolve().parent.parent / "models" / "tts"
MODEL = "elevenlabs/eleven-v4-turbo"
HEADERS = {
    "Authorization": "Bearer test-key",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://dify.ai/",
    "X-Title": "Dify",
}


def load_schemas() -> list[AIModelEntity]:
    return [
        AIModelEntity.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(TTS_DIR.glob("*.yaml"))
        if not path.name.startswith("_")
    ]


def audio_response(chunks: list[bytes], status_code: int = 200, error: str = "") -> MagicMock:
    response = MagicMock()
    response.ok = 200 <= status_code < 300
    response.status_code = status_code
    response.iter_content.return_value = iter(chunks)
    response.json.return_value = {"error": {"message": error, "code": status_code}}
    response.__enter__.return_value = response
    return response


class TestTTSModelSchemas(unittest.TestCase):
    def test_position_list_matches_shipped_schemas(self) -> None:
        positions = yaml.safe_load((TTS_DIR / "_position.yaml").read_text(encoding="utf-8"))
        self.assertEqual(sorted(positions), sorted(schema.model for schema in load_schemas()))

    def test_every_schema_streams_mp3_with_a_known_default_voice(self) -> None:
        for schema in load_schemas():
            with self.subTest(model=schema.model):
                properties = schema.model_properties
                self.assertEqual(schema.model_type, ModelType.TTS)
                self.assertEqual(properties[ModelPropertyKey.AUDIO_TYPE], "mp3")
                modes = [voice["mode"] for voice in properties[ModelPropertyKey.VOICES]]
                self.assertEqual(len(modes), len(set(modes)))
                self.assertIn(properties[ModelPropertyKey.DEFAULT_VOICE], modes)
                self.assertTrue(
                    all(voice["language"] for voice in properties[ModelPropertyKey.VOICES])
                )
                self.assertIsNotNone(schema.pricing)


class TestOpenRouterText2SpeechModel(unittest.TestCase):
    def setUp(self) -> None:
        self.tts = OpenRouterText2SpeechModel(model_schemas=load_schemas())

    @patch("models._audio_utils.requests.post")
    def test_invoke_streams_audio_from_openrouter(self, mock_post: Mock) -> None:
        mock_post.return_value = audio_response([b"ID3", b"audio"])

        result = self.tts._invoke(
            model=MODEL,
            tenant_id="tenant",
            credentials={"api_key": "test-key"},
            content_text="Hello world.",
            voice="sarah",
        )

        self.assertEqual(b"".join(result), b"ID3audio")
        mock_post.assert_called_once_with(
            "https://openrouter.ai/api/v1/audio/speech",
            timeout=(10, 300),
            headers=HEADERS,
            json={
                "model": MODEL,
                "input": "Hello world.",
                "response_format": "mp3",
                "voice": "sarah",
            },
            stream=True,
        )

    @patch("models._audio_utils.requests.post")
    def test_unknown_voice_falls_back_to_default_voice(self, mock_post: Mock) -> None:
        mock_post.return_value = audio_response([b"audio"])

        b"".join(
            self.tts._invoke(
                model=MODEL,
                tenant_id="tenant",
                credentials={"api_key": "test-key"},
                content_text="Hello",
                voice="alloy",
            )
        )

        self.assertEqual(mock_post.call_args.kwargs["json"]["voice"], "george")

    @patch("models._audio_utils.requests.post")
    def test_long_text_is_split_by_word_limit(self, mock_post: Mock) -> None:
        mock_post.side_effect = lambda *args, **kwargs: audio_response([b"x"])
        sentence = "a" * 1500 + ". "
        text = sentence * 3

        audio = b"".join(
            self.tts._invoke(
                model=MODEL,
                tenant_id="tenant",
                credentials={
                    "api_key": "test-key",
                    "endpoint_url": " https://openrouter.example.com/api/v1/ ",
                },
                content_text=text,
                voice="george",
            )
        )

        self.assertEqual(audio, b"xxx")
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(
            mock_post.call_args.args[0], "https://openrouter.example.com/api/v1/audio/speech"
        )
        for call in mock_post.call_args_list:
            self.assertLessEqual(len(call.kwargs["json"]["input"]), 2000)

    def test_empty_text_is_rejected_without_calling_api(self) -> None:
        with patch("models._audio_utils.requests.post") as mock_post:
            with self.assertRaises(InvokeBadRequestError):
                self.tts._invoke(
                    model=MODEL,
                    tenant_id="tenant",
                    credentials={"api_key": "test-key"},
                    content_text="   ",
                    voice="george",
                )
            mock_post.assert_not_called()

    def test_missing_api_key_is_authorization_error(self) -> None:
        result = self.tts._invoke(
            model=MODEL, tenant_id="t", credentials={}, content_text="Hi", voice="george"
        )
        with self.assertRaises(InvokeAuthorizationError):
            next(result)

    @patch("models._audio_utils.requests.post")
    def test_http_errors_map_to_dify_errors_with_openrouter_detail(self, mock_post: Mock) -> None:
        cases = [
            (400, InvokeBadRequestError),
            (401, InvokeAuthorizationError),
            (402, InvokeBadRequestError),
            (429, InvokeRateLimitError),
            (502, InvokeServerUnavailableError),
        ]
        for status_code, expected_error in cases:
            with self.subTest(status_code=status_code):
                mock_post.return_value = audio_response([], status_code, "Voice not supported")
                result = self.tts._invoke(
                    model=MODEL,
                    tenant_id="t",
                    credentials={"api_key": "test-key"},
                    content_text="Hi",
                    voice="george",
                )
                with self.assertRaises(expected_error) as ctx:
                    next(result)
                self.assertIn(str(status_code), str(ctx.exception))
                self.assertIn("Voice not supported", str(ctx.exception))

    @patch("models._audio_utils.requests.post")
    def test_network_errors_map_to_connection_error(self, mock_post: Mock) -> None:
        for exception in (requests.exceptions.Timeout(), requests.exceptions.ConnectionError()):
            with self.subTest(exception=type(exception).__name__):
                mock_post.side_effect = exception
                result = self.tts._invoke(
                    model=MODEL,
                    tenant_id="t",
                    credentials={"api_key": "test-key"},
                    content_text="Hi",
                    voice="george",
                )
                with self.assertRaises(InvokeConnectionError):
                    next(result)

    @patch("models._audio_utils.requests.post")
    def test_validate_credentials_uses_default_voice(self, mock_post: Mock) -> None:
        mock_post.return_value = audio_response([b"audio"])

        self.tts.validate_credentials(model=MODEL, credentials={"api_key": "test-key"})

        self.assertEqual(mock_post.call_args.kwargs["json"]["voice"], "george")

    @patch("models._audio_utils.requests.post")
    def test_validate_credentials_wraps_failures(self, mock_post: Mock) -> None:
        mock_post.return_value = audio_response([], 401, "Invalid key")

        with self.assertRaises(CredentialsValidateFailedError):
            self.tts.validate_credentials(model=MODEL, credentials={"api_key": "bad"})

    @patch("models._audio_utils.requests.post")
    def test_public_invoke_returns_audio_generator(self, mock_post: Mock) -> None:
        mock_post.return_value = audio_response([b"a", b"b"])

        result = self.tts.invoke(
            model=MODEL,
            tenant_id="t",
            credentials={"api_key": "test-key"},
            content_text="Hi",
            voice="george",
        )

        self.assertEqual(b"".join(result), b"ab")
        self.assertEqual(self.tts.get_tts_model_mime_type(MODEL, {}), "audio/mpeg")


if __name__ == "__main__":
    unittest.main()
