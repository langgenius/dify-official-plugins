import json
import logging
from abc import ABC
from collections.abc import Iterator
from typing import Any, Optional

import requests
from dify_plugin.entities.model import ModelPropertyKey
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.tts_model import TTSModel

logger = logging.getLogger(__name__)


class MinimaxText2SpeechModel(TTSModel, ABC):
    """
    Minimax Text-to-Speech Model
    """

    def validate_credentials(self, model: str, credentials: dict, user: Optional[str] = None) -> None:
        """
        validate credentials text2speech model

        :param model: model name
        :param credentials: model credentials
        :param user: unique user id
        :return: text translated to audio file
        """
        try:
            self._invoke(
                model=model,
                tenant_id="",
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _invoke(
        self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str, user: Optional[str] = None
    ) -> Iterator[bytes]:
        """
        Invoke TTS model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: voice to use
        :param user: unique user id
        :return: audio chunks
        """
        group_id = credentials.get("minimax_group_id")
        api_key = credentials.get("minimax_api_key")

        if not group_id or not api_key:
            raise InvokeAuthorizationError("Missing required credentials: group_id and api_key")

        # Get endpoint_url from credentials, use correct default if not provided
        endpoint_url = credentials.get("endpoint_url", "https://api.minimaxi.com")
        base_url = endpoint_url.rstrip('/')
        url = f"{base_url}/v1/t2a_v2?GroupId={group_id}"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        # Build request body with all supported parameters
        body_data = {
            "model": model,
            "text": content_text,
            "stream": True,
            "voice_setting": {
                "voice_id": voice,
                "speed": float(credentials.get("speed", 1.0)),
                "vol": float(credentials.get("vol", 1.0)),
                "pitch": int(credentials.get("pitch", 0))
            },
            "audio_setting": {
                "sample_rate": int(credentials.get("sample_rate", 32000)),
                "bitrate": int(credentials.get("bitrate", 128000)),
                "format": credentials.get("format", "mp3"),
                "channel": int(credentials.get("channel", 1))
            }
        }

        # Add pronunciation dictionary if provided
        pronunciation_dict = credentials.get("pronunciation_dict")
        if pronunciation_dict:
            body_data["pronunciation_dict"] = pronunciation_dict

        body = json.dumps(body_data)

        try:
            response = requests.post(url, headers=headers, data=body, stream=True)
            response.raise_for_status()

            # Process streaming response according to correct format
            for chunk in response.raw:
                if chunk:
                    if chunk[:5] == b'data:':
                        try:
                            data = json.loads(chunk[5:])
                            if "data" in data and "extra_info" not in data:
                                if "audio" in data["data"]:
                                    audio_hex = data["data"]["audio"]
                                    yield bytes.fromhex(audio_hex)
                        except (json.JSONDecodeError, ValueError, KeyError) as e:
                            logger.warning(f"Failed to parse chunk: {e}")
                            continue

        except requests.exceptions.RequestException as e:
            raise self._transform_invoke_error(e, model)

    def _get_model_entity(self, model: str) -> Optional[Any]:
        """
        Get model entity from predefined models

        :param model: model name
        :return: model entity or None
        """
        models = self.predefined_models()
        for model_entity in models:
            if model_entity.model == model:
                return model_entity
        return None

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeConnectionError: [requests.exceptions.ConnectionError],
            InvokeServerUnavailableError: [requests.exceptions.HTTPError, requests.exceptions.Timeout],
            InvokeRateLimitError: [requests.exceptions.TooManyRedirects],
            InvokeAuthorizationError: [requests.exceptions.HTTPError, ValueError],
            InvokeBadRequestError: [requests.exceptions.RequestException, KeyError, json.JSONDecodeError],
        }

    def _get_model_default_voice(self, model: str, credentials: dict) -> Any:
        """
        Get model default voice from YAML configuration
        """
        model_entity = self._get_model_entity(model)
        if model_entity and model_entity.model_properties:
            return model_entity.model_properties.get(ModelPropertyKey.DEFAULT_VOICE)
        return "male-qn-qingse"  # fallback

    def _get_model_word_limit(self, model: str, credentials: dict) -> int:
        """
        Get model word limit from YAML configuration
        """
        model_entity = self._get_model_entity(model)
        if model_entity and model_entity.model_properties:
            return model_entity.model_properties.get(ModelPropertyKey.WORD_LIMIT, 8000)
        return 8000  # fallback

    def _get_model_audio_type(self, model: str, credentials: dict) -> str:
        """
        Get model audio type from YAML configuration
        """
        model_entity = self._get_model_entity(model)
        if model_entity and model_entity.model_properties:
            return model_entity.model_properties.get(ModelPropertyKey.AUDIO_TYPE, "mp3")
        return "mp3"  # fallback

    def _get_model_workers_limit(self, model: str, credentials: dict) -> int:
        """
        Get model workers limit from YAML configuration
        """
        model_entity = self._get_model_entity(model)
        if model_entity and model_entity.model_properties:
            return model_entity.model_properties.get(ModelPropertyKey.MAX_WORKERS, 5)
        return 5  # fallback

    def get_tts_model_voices(self, model: str, credentials: dict, language: Optional[str] = None) -> list:
        """
        Get available voices for the model from YAML configuration
        """
        model_entity = self._get_model_entity(model)
        if not model_entity or not model_entity.model_properties:
            return []

        voices = model_entity.model_properties.get(ModelPropertyKey.VOICES, [])

        # Convert YAML voice format to expected format
        formatted_voices = []
        for voice in voices:
            formatted_voice = {
                "name": voice.get("name", ""),
                "value": voice.get("mode", ""),
                "language": voice.get("language", [])
            }
            formatted_voices.append(formatted_voice)

        if language:
            return [v for v in formatted_voices if language in v.get("language", [])]
        return formatted_voices
