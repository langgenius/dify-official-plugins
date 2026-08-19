import base64
import json
import logging
from collections.abc import Generator
from typing import Mapping
from urllib.parse import urljoin

import requests

from dify_plugin.entities.model import AIModelEntity, I18nObject
from dify_plugin.errors.model import InvokeBadRequestError
from dify_plugin.interfaces.model.openai_compatible.tts import OAICompatText2SpeechModel

logger = logging.getLogger(__name__)


class OpenAIText2SpeechModel(OAICompatText2SpeechModel):

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        entity = super().get_customizable_model_schema(model, credentials)

        if "display_name" in credentials and credentials["display_name"] != "":
            entity.label = I18nObject(
                en_us=credentials["display_name"], zh_hans=credentials["display_name"]
            )

        return entity

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: str | None = None,
    ) -> Generator[bytes, None, None]:
        """
        Invoke TTS model.

        Routes to BytePlus TTS or standard OpenAI-compatible TTS based on
        the 'tts_api_format' credential.
        """
        tts_api_format = credentials.get("tts_api_format", "openai")

        if tts_api_format == "byteplus":
            yield from self._invoke_byteplus(
                model=model,
                credentials=credentials,
                content_text=content_text,
                voice=voice,
            )
        else:
            # Delegate to the parent OpenAI-compatible implementation
            yield from super()._invoke(
                model=model,
                tenant_id=tenant_id,
                credentials=credentials,
                content_text=content_text,
                voice=voice,
                user=user,
            )

    def _invoke_byteplus(
        self,
        model: str,
        credentials: dict,
        content_text: str,
        voice: str,
    ) -> Generator[bytes, None, None]:
        """
        Invoke BytePlus TTS HTTP unidirectional streaming API.

        Endpoint format: {base_url}/tts/unidirectional
        Auth: x-api-key header
        Response: JSON Lines (NDJSON) with base64-encoded audio in 'data' field.
        """
        api_key = credentials.get("api_key", "")
        resource_id = credentials.get("tts_resource_id", "").strip() or model
        sample_rate = int(credentials.get("tts_sample_rate", "24000"))
        audio_format = self._get_model_audio_type(model, credentials) or "mp3"

        # Build endpoint URL: user provides base like https://...com/api/v3
        # We append /tts/unidirectional
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        if not endpoint_url:
            raise InvokeBadRequestError("endpoint_url is required for BytePlus TTS")
        endpoint_url = endpoint_url + "/tts/unidirectional"

        # Headers
        headers = {
            "x-api-key": api_key,
            "X-Api-Resource-Id": resource_id,
            "Content-Type": "application/json",
            "Connection": "keep-alive",
        }

        # Additions config (enables language detection, markdown filter, caching)
        additions = {
            "disable_markdown_filter": True,
            "enable_language_detector": True,
            "cache_config": {"text_type": 1, "use_cache": True},
        }

        # Split text into chunks based on word limit
        word_limit = self._get_model_word_limit(model, credentials)
        sentences = self._split_text_into_sentences(content_text, word_limit or 2000)

        for sentence in sentences:
            payload = {
                "req_params": {
                    "text": sentence,
                    "speaker": voice,
                    "additions": json.dumps(additions),
                    "audio_params": {
                        "format": audio_format,
                        "sample_rate": sample_rate,
                    },
                },
            }

            try:
                response = requests.post(
                    endpoint_url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=(10, 300),
                )
            except requests.exceptions.RequestException as e:
                raise InvokeBadRequestError(
                    f"BytePlus TTS request failed: {type(e).__name__}: {e}"
                ) from e

            if response.status_code != 200:
                raise InvokeBadRequestError(
                    f"BytePlus TTS returned HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            # Parse NDJSON streaming response
            try:
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    data = json.loads(line)
                    code = data.get("code", 0)

                    if code == 0 and data.get("data"):
                        # Decode base64 audio chunk and yield
                        chunk_audio = base64.b64decode(data["data"])
                        yield chunk_audio
                    elif code == 20000000:
                        # Stream finished successfully
                        break
                    elif code > 0:
                        raise InvokeBadRequestError(
                            f"BytePlus TTS error (code={code}): "
                            f"{data.get('message', 'unknown error')}"
                        )
            except json.JSONDecodeError as e:
                raise InvokeBadRequestError(
                    f"BytePlus TTS returned invalid JSON: {e}"
                ) from e
            finally:
                response.close()
