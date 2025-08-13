import concurrent.futures
from functools import reduce
from io import BytesIO
from json import dumps
from typing import Optional

import requests
from pydub import AudioSegment

from dify_plugin import TTSModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelPropertyKey,
    ModelType,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeServerUnavailableError,
)


class Ai302TextToSpeechModel(TTSModel):
    """
    Model class for 302.AI text to speech model.
    """

    api_base: str = "https://api.302.ai"

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> bytes:
        """
        Invoke text to speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to convert to speech
        :param voice: voice to use
        :param user: unique user id
        :return: audio file content as bytes
        """
        # Get available voices and validate
        voices = self.get_tts_model_voices(model=model, credentials=credentials)
        if not voices:
            raise InvokeBadRequestError("No voices found for the model")

        if not voice or voice not in [d["value"] for d in voices]:
            voice = self._get_model_default_voice(model, credentials)

        return self._tts_invoke(
            model=model, credentials=credentials, content_text=content_text, voice=voice
        )

    def _tts_invoke(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> bytes:
        """
        Invoke TTS model API

        :param model: model name
        :param credentials: model credentials
        :param content_text: text content to be converted
        :param voice: model voice
        :return: audio file as bytes
        """
        api_key = credentials["api_key"]
        if not api_key:
            raise CredentialsValidateFailedError("api_key is required")

        base_url = credentials.get("base_url", self.api_base)
        if base_url.endswith("/"):
            base_url = base_url[:-1]

        url = base_url + "/302/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Prepare request data
        data = {
            "model": model,
            "input": content_text.strip(),
            "voice": voice,
            "response_format": "mp3",  # Default format
        }

        try:
            # Handle long text by splitting into sentences
            word_limit = self._get_model_word_limit(model, credentials) or 4096
            if len(content_text) > word_limit:
                return self._process_long_text(
                    model=model,
                    credentials=credentials, 
                    content_text=content_text,
                    voice=voice,
                    word_limit=word_limit
                )
            
            # Single request for short text
            response = requests.post(url, headers=headers, data=dumps(data), timeout=60)
            
            if response.status_code != 200:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                except Exception:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                
                if response.status_code == 401:
                    raise InvokeAuthorizationError(error_msg)
                elif response.status_code == 400:
                    raise InvokeBadRequestError(error_msg)
                elif response.status_code >= 500:
                    raise InvokeServerUnavailableError(error_msg)
                else:
                    raise InvokeBadRequestError(error_msg)

            return response.content

        except requests.RequestException as e:
            raise InvokeConnectionError(str(e))
        except Exception as e:
            raise InvokeBadRequestError(str(e))

    def _process_long_text(
        self,
        model: str,
        credentials: dict,
        content_text: str,
        voice: str,
        word_limit: int,
    ) -> bytes:
        """
        Process long text by splitting into chunks and combining audio

        :param model: model name
        :param credentials: model credentials
        :param content_text: long text content
        :param voice: voice to use
        :param word_limit: maximum words per request
        :return: combined audio bytes
        """
        sentences = list(
            self._split_text_into_sentences(
                org_text=content_text, max_length=word_limit
            )
        )
        
        if not sentences:
            raise InvokeBadRequestError("No sentences to process")

        audio_bytes_list = []
        max_workers = min(3, len(sentences))  # Limit concurrent requests

        # Process sentences concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    self._process_sentence,
                    sentence=sentence,
                    model=model,
                    voice=voice,
                    credentials=credentials,
                )
                for sentence in sentences
            ]
            
            for future in futures:
                try:
                    result = future.result()
                    if result:
                        audio_bytes_list.append(result)
                except Exception as ex:
                    raise InvokeBadRequestError(f"Failed to process sentence: {str(ex)}")

        if not audio_bytes_list:
            raise InvokeBadRequestError("No audio bytes generated")

        # Combine audio segments
        try:
            audio_segments = [
                AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
                for audio_bytes in audio_bytes_list
                if audio_bytes
            ]
            
            if not audio_segments:
                raise InvokeBadRequestError("No valid audio segments")
            
            combined_segment = reduce(lambda x, y: x + y, audio_segments)
            buffer = BytesIO()
            combined_segment.export(buffer, format="mp3")
            buffer.seek(0)
            
            return buffer.read()
        except Exception as ex:
            raise InvokeBadRequestError(f"Failed to combine audio: {str(ex)}")

    def _process_sentence(
        self, sentence: str, model: str, voice: str, credentials: dict
    ) -> bytes:
        """
        Process a single sentence

        :param sentence: sentence to convert
        :param model: model name  
        :param voice: voice to use
        :param credentials: model credentials
        :return: audio bytes
        """
        api_key = credentials["api_key"]
        base_url = credentials.get("base_url", self.api_base)
        if base_url.endswith("/"):
            base_url = base_url[:-1]

        url = base_url + "/302/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": model,
            "input": sentence.strip(),
            "voice": voice,
            "response_format": "mp3",
        }

        try:
            response = requests.post(url, headers=headers, data=dumps(data), timeout=30)
            response.raise_for_status()
            return response.content
        except Exception as e:
            raise InvokeBadRequestError(f"Failed to process sentence: {str(e)}")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        validate credentials text2speech model

        :param model: model name
        :param credentials: model credentials
        :param user: unique user id
        :return: text translated to audio file
        """
        try:
            # Test with a short text
            self._tts_invoke(
                model=model,
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    @property
    def _invoke_error_mapping(self) -> dict:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [InvokeBadRequestError],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        Generate custom model entities from credentials
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.TTS,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size") or 4096
                )
            },
        )

        return entity
