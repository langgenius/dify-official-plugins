import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _install_test_stubs() -> None:
    if "httpx" not in sys.modules:
        httpx_module = types.ModuleType("httpx")

        class Timeout:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        httpx_module.Timeout = Timeout
        sys.modules["httpx"] = httpx_module

    if "openai" not in sys.modules:
        openai_module = types.ModuleType("openai")

        class OpenAI:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class AzureOpenAI(OpenAI):
            pass

        class OpenAIError(Exception):
            pass

        openai_module.OpenAI = OpenAI
        openai_module.AzureOpenAI = AzureOpenAI
        openai_module.APIConnectionError = OpenAIError
        openai_module.APITimeoutError = OpenAIError
        openai_module.InternalServerError = OpenAIError
        openai_module.RateLimitError = OpenAIError
        openai_module.AuthenticationError = OpenAIError
        openai_module.PermissionDeniedError = OpenAIError
        openai_module.BadRequestError = OpenAIError
        openai_module.NotFoundError = OpenAIError
        openai_module.UnprocessableEntityError = OpenAIError
        openai_module.APIError = OpenAIError
        sys.modules["openai"] = openai_module

    if "dify_plugin.entities.model" not in sys.modules:
        entities_model = types.ModuleType("dify_plugin.entities.model")
        entities_model.AIModelEntity = type("AIModelEntity", (), {})
        sys.modules["dify_plugin.entities.model"] = entities_model

    if "dify_plugin.errors.model" not in sys.modules:
        errors_model = types.ModuleType("dify_plugin.errors.model")

        class CredentialsValidateFailedError(Exception):
            pass

        class InvokeBadRequestError(Exception):
            pass

        class InvokeAuthorizationError(Exception):
            pass

        class InvokeConnectionError(Exception):
            pass

        class InvokeError(Exception):
            pass

        class InvokeRateLimitError(Exception):
            pass

        class InvokeServerUnavailableError(Exception):
            pass

        errors_model.CredentialsValidateFailedError = CredentialsValidateFailedError
        errors_model.InvokeBadRequestError = InvokeBadRequestError
        errors_model.InvokeAuthorizationError = InvokeAuthorizationError
        errors_model.InvokeConnectionError = InvokeConnectionError
        errors_model.InvokeError = InvokeError
        errors_model.InvokeRateLimitError = InvokeRateLimitError
        errors_model.InvokeServerUnavailableError = InvokeServerUnavailableError
        sys.modules["dify_plugin.errors.model"] = errors_model

    if "dify_plugin.interfaces.model.tts_model" not in sys.modules:
        tts_model_module = types.ModuleType("dify_plugin.interfaces.model.tts_model")

        class TTSModel:
            pass

        tts_model_module.TTSModel = TTSModel
        sys.modules["dify_plugin.interfaces.model.tts_model"] = tts_model_module

    if "models.constants" not in sys.modules:
        constants_module = types.ModuleType("models.constants")

        class AzureBaseModel:
            pass

        constants_module.AZURE_OPENAI_API_VERSION = "2024-02-15-preview"
        constants_module.AzureBaseModel = AzureBaseModel
        constants_module.TTS_BASE_MODELS = []
        sys.modules["models.constants"] = constants_module


_install_test_stubs()

from models.tts.tts import AzureOpenAIText2SpeechModel


class _StreamingResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_bytes(self, chunk_size: int):
        yield b"chunk-1"
        yield b"chunk-2"


class AzureOpenAITTSTestCase(unittest.TestCase):
    def test_streaming_uses_model_audio_type_for_response_format(self):
        captured_kwargs = {}

        def create(**kwargs):
            captured_kwargs.update(kwargs)
            return _StreamingResponse()

        model = AzureOpenAIText2SpeechModel.__new__(AzureOpenAIText2SpeechModel)
        model._create_client = Mock(
            return_value=types.SimpleNamespace(
                audio=types.SimpleNamespace(
                    speech=types.SimpleNamespace(
                        with_streaming_response=types.SimpleNamespace(create=create)
                    )
                )
            )
        )
        model._get_model_audio_type = Mock(return_value="wav")

        chunks = list(
            model._tts_invoke_streaming(
                model="gpt-4o-mini-tts",
                credentials={"openai_api_base": "https://example.com"},
                content_text="hello world",
                voice="alloy",
            )
        )

        self.assertEqual(chunks, [b"chunk-1", b"chunk-2"])
        self.assertEqual(captured_kwargs["response_format"], "wav")
        model._get_model_audio_type.assert_called_once_with(
            "gpt-4o-mini-tts", {"openai_api_base": "https://example.com"}
        )


if __name__ == "__main__":
    unittest.main()
