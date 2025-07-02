from typing import Generator, Mapping, Optional
from dify_plugin.entities.model import AIModelEntity
import httpx
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError
)
from dify_plugin.entities import I18nObject
from dify_plugin import TTSModel
from dify_plugin.entities.model import ModelType, ModelPropertyKey

from fish_audio_sdk import Session, TTSRequest

class FishAudioText2SpeechModel(TTSModel):
    """
    Model class for Fish.audio Text to Speech model.
    """

    def get_tts_model_voices(self, model: str, credentials: dict, language: Optional[str] = None) -> Optional[list]:
        if "voices" in credentials and credentials["voices"]:
            return credentials["voices"]

        api_base = credentials.get("api_base", "https://api.fish.audio")
        api_key = credentials.get("api_key")
        use_public_models = credentials.get("use_public_models", "false") == "true"
        session = Session(api_key, base_url=api_base)
        params = {
            "self_only": not use_public_models,
            "page_size": 100,
        }
        if language is not None:
            if "-" in language:
                language = language.split("-")[0]
            params["language"] = language
        results = session.list_models(**params)
        return [{"name": i.title, "value": i.id} for i in results.items]

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> bytes | Generator[bytes, None, None]:
        """
        Invoke text2speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param voice: model timbre
        :param content_text: text content to be translated
        :param user: unique user id
        :return: text translated to audio file
        """

        return self._tts_invoke_streaming(
            model=model,
            credentials=credentials,
            content_text=content_text,
            voice=voice,
        )

    def validate_credentials(
            self, model: str, credentials: dict, user: Optional[str] = None
    ) -> None:
        """
        Validate credentials for text2speech model

        :param credentials: model credentials
        :param user: unique user id
        """
        api_key = credentials.get("api_key")
        api_base = credentials.get("api_base")
        session = Session(api_key, base_url=api_base)
        try:
            session.list_models(self_only=True)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))
    def _tts_invoke_streaming(self, model: str, credentials: dict, content_text: str, voice: str) -> Generator[bytes, None, None]:
        """
        Invoke streaming text2speech model
        :param model: model name
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: ID of the reference audio (if any)
        :return: generator yielding audio chunks
        """

        try:
            word_limit = self._get_model_word_limit(model, credentials) or 500
            if len(content_text) > word_limit:
                sentences = self._split_text_into_sentences(content_text, max_length=word_limit)
            else:
                sentences = [content_text.strip()]

            for i in range(len(sentences)):
                yield from self._tts_invoke_streaming_sentence(
                    model=model, credentials=credentials, content_text=sentences[i], voice=voice
                )

        except Exception as ex:
            raise InvokeBadRequestError(str(ex))

    def _tts_invoke_streaming_sentence(self, model: str, credentials: dict, content_text: str, voice: Optional[str] = None) -> Generator[bytes, None, None]:
        """
        Invoke streaming text2speech model

        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: ID of the reference audio (if any)
        :return: generator yielding audio chunks
        """
        api_key = credentials.get("api_key")
        api_base = credentials.get("api_base", "https://api.fish.audio")
        latency = credentials.get("latency", "normal")
        session = Session(api_key, base_url=api_base)
        request = TTSRequest(
            text=content_text,
            format="mp3",
            reference_id=voice,
            latency=latency
        )
        try:
            gen = session.tts(request,backend=model)
            return gen
        except Exception as e:
            raise e

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeBadRequestError: [
                httpx.HTTPStatusError,
            ],
        }
