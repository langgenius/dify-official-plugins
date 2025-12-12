import json
import logging
import time
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


class ShengsuanyunTTSModel(TTSModel, ABC):
    """
    Shengsuanyun Text-to-Speech Model using async task API
    """

    # Default API endpoint (includes /v1 to match provider config)
    DEFAULT_ENDPOINT = "https://router.shengsuanyun.com/api/v1"
    
    # Task status constants
    STATUS_SUBMITTING = "SUBMITTING"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_PENDING = "PENDING"
    STATUS_QUEUED = "QUEUED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_TIMEOUT = "TIMEOUT"
    STATUS_UNKNOWN = "UNKNOWN"
    
    # Polling configuration
    MAX_POLL_ATTEMPTS = 120  # Maximum number of polling attempts
    POLL_INTERVAL = 2  # Seconds between polls

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
        Invoke TTS model using async task API

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: voice to use
        :param user: unique user id
        :return: audio chunks
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise InvokeAuthorizationError("Missing required credentials: api_key")

        base_url = credentials.get("base_url", self.DEFAULT_ENDPOINT).rstrip('/')
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        request_id = self._submit_task(base_url, headers, model, content_text, voice, credentials)
        audio_urls = self._poll_task_status(base_url, headers, request_id)
        if audio_urls:
            for audio_url in audio_urls:
                yield from self._download_audio(audio_url, headers)

    def _submit_task(
        self, base_url: str, headers: dict, model: str, content_text: str, voice: str, credentials: dict
    ) -> str:
        """
        Submit async TTS task

        :param base_url: API base URL
        :param headers: request headers
        :param model: model name
        :param content_text: text content to be translated
        :param voice: voice to use
        :param credentials: model credentials
        :return: request_id for polling
        """
        url = f"{base_url}/tasks/generations"
        body_data = {
            "model": model,
            "text": content_text,
            "voice_id": voice,
            "speed": float(credentials.get("speed", 1.0)),
            "vol": float(credentials.get("vol", 1.0)),
            "pitch": int(credentials.get("pitch", 0)),
            "sample_rate": int(credentials.get("sample_rate", 32000)),
            "bitrate": int(credentials.get("bitrate", 128000)),
            "format": credentials.get("format", "mp3"),
            "channel": int(credentials.get("channel", 1))
        }

        # Add pronunciation dictionary if provided
        pronunciation_dict = credentials.get("pronunciation_dict")
        if pronunciation_dict:
            body_data["pronunciation_dict"] = pronunciation_dict

        # Add callback_url if provided
        callback_url = credentials.get("callback_url")
        if callback_url:
            body_data["callback_url"] = callback_url

        try:
            logger.info(f"Submitting TTS task to {url} with body: {body_data}")
            response = requests.post(url, headers=headers, json=body_data, timeout=30)
            
            # Try to get error details from response body before raising
            try:
                result = response.json()
                logger.info(f"API response: {result}")
            except json.JSONDecodeError:
                result = {}
            
            if not response.ok:
                error_message = result.get("message", response.text or f"HTTP {response.status_code}")
                raise InvokeBadRequestError(f"Task submission failed: {error_message}")
            
            if result.get("code") != "success":
                error_message = result.get("message", "Unknown error")
                raise InvokeBadRequestError(f"Task submission failed: {error_message}")
            
            data = result.get("data", {})
            request_id = data.get("request_id")
            
            if not request_id:
                raise InvokeBadRequestError("No request_id returned from task submission")
            
            logger.info(f"Task submitted successfully, request_id: {request_id}")
            return request_id
            
        except requests.exceptions.RequestException as e:
            raise self._transform_invoke_error(e)

    def _poll_task_status(self, base_url: str, headers: dict, request_id: str) -> list[str]:
        """
        Poll task status until completion

        :param base_url: API base URL
        :param headers: request headers
        :param request_id: task request ID
        :return: list of audio URLs
        """
        url = f"{base_url}/tasks/generations/{request_id}"
        
        terminal_statuses = {
            self.STATUS_COMPLETED,
            self.STATUS_FAILED,
            self.STATUS_CANCELLED,
            self.STATUS_TIMEOUT
        }
        
        for attempt in range(self.MAX_POLL_ATTEMPTS):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get("code") != "success":
                    error_message = result.get("message", "Unknown error")
                    raise InvokeBadRequestError(f"Task query failed: {error_message}")
                
                data = result.get("data", {})
                status = data.get("status", self.STATUS_UNKNOWN)
                progress = data.get("progress", "0%")
                
                logger.debug(f"Task {request_id} status: {status}, progress: {progress}")
                
                if status == self.STATUS_COMPLETED:
                    result_data = data.get("data", {})
                    audio_urls = result_data.get("audio_urls", [])
                    
                    if not audio_urls:
                        raise InvokeBadRequestError("Task completed but no audio URLs returned")
                    
                    logger.info(f"Task {request_id} completed, audio URLs: {audio_urls}")
                    return audio_urls
                
                elif status == self.STATUS_FAILED:
                    fail_reason = data.get("fail_reason", "Unknown failure reason")
                    raise InvokeBadRequestError(f"Task failed: {fail_reason}")
                
                elif status == self.STATUS_CANCELLED:
                    raise InvokeBadRequestError("Task was cancelled")
                
                elif status == self.STATUS_TIMEOUT:
                    raise InvokeServerUnavailableError("Task timed out on server")
                
                elif status in terminal_statuses:
                    raise InvokeBadRequestError(f"Task ended with status: {status}")
                
                # Task still in progress, wait and retry
                time.sleep(self.POLL_INTERVAL)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error polling task status (attempt {attempt + 1}): {e}")
                if attempt < self.MAX_POLL_ATTEMPTS - 1:
                    time.sleep(self.POLL_INTERVAL)
                else:
                    raise InvokeServerUnavailableError(f"Failed to poll task status after {self.MAX_POLL_ATTEMPTS} attempts")
        
        raise InvokeServerUnavailableError(f"Task did not complete within {self.MAX_POLL_ATTEMPTS * self.POLL_INTERVAL} seconds")

    def _download_audio(self, audio_url: str, headers: dict) -> Iterator[bytes]:
        """
        Download audio from URL and yield chunks

        :param audio_url: URL to download audio from
        :param headers: request headers (may be used for authenticated downloads)
        :return: audio chunks
        """
        try:
            # Download audio - may or may not need auth headers depending on URL
            response = requests.get(audio_url, stream=True, timeout=60)
            response.raise_for_status()
            
            # Yield audio content in chunks
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download audio from {audio_url}: {e}")
            raise InvokeServerUnavailableError(f"Failed to download audio: {e}")

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
