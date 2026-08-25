import concurrent.futures
import copy
from typing import Any, Optional
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
)
from dify_plugin.interfaces.model.tts_model import TTSModel
from ..common import _CommonAzureOpenAI
from ..constants import TTS_BASE_MODELS, AzureBaseModel


class AzureOpenAIText2SpeechModel(_CommonAzureOpenAI, TTSModel):
    """
    Model class for OpenAI Speech to text model.
    """

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> Any:
        """
        _invoke text2speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :param user: unique user id
        :return: text translated to audio file
        """
        if not voice or voice not in [
            d["value"]
            for d in self.get_tts_model_voices(model=model, credentials=credentials)
        ]:
            voice = self._get_model_default_voice(model, credentials)
        return self._tts_invoke_streaming(
            model=model, credentials=credentials, content_text=content_text, voice=voice
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        validate credentials text2speech model

        :param model: model name
        :param credentials: model credentials
        :return: text translated to audio file
        """
        try:
            self._tts_invoke_streaming(
                model=model,
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
                use_cache=False,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str, *, use_cache: bool = True
    ) -> Any:
        """
        _tts_invoke_streaming text2speech model
        :param model: model name
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :return: text translated to audio file
        """
        try:
            client = self._create_client(credentials, use_cache=use_cache)
            audio_type = self._get_model_audio_type(model, credentials)
            max_length = 3500
            if len(content_text) > max_length:
                sentences = self._split_text_into_sentences(
                    content_text, max_length=max_length
                )
                # The OpenAI SDK's with_streaming_response.create returns a
                # deferred context manager: the HTTP request fires on
                # __enter__, not on .create(). Fetch each sentence inside a
                # worker (real parallelism), buffer the bytes, and yield them
                # in order. Contexts and the executor always close.
                def _fetch_sentence_audio(sentence: str) -> bytes:
                    with client.audio.speech.with_streaming_response.create(
                        model=model,
                        response_format=audio_type,
                        input=sentence,
                        voice=voice,
                    ) as response:
                        return b"".join(response.iter_bytes(1024))

                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(3, len(sentences))
                ) as executor:
                    futures = [
                        executor.submit(_fetch_sentence_audio, sentence)
                        for sentence in sentences
                    ]
                    for future in futures:
                        yield future.result()
            else:
                with client.audio.speech.with_streaming_response.create(
                    model=model,
                    voice=voice,
                    response_format=audio_type,
                    input=content_text.strip(),
                ) as response:
                    yield from response.iter_bytes(1024)
        except Exception as ex:
            raise InvokeBadRequestError(str(ex))

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        base_model_name = self._get_base_model_name(credentials)
        ai_model_entity = self._get_ai_model_entity(base_model_name, model)
        return ai_model_entity.entity if ai_model_entity else None

    @staticmethod
    def _get_ai_model_entity(base_model_name: str, model: str) -> AzureBaseModel | None:
        for ai_model_entity in TTS_BASE_MODELS:
            if ai_model_entity.base_model_name == base_model_name:
                ai_model_entity_copy = copy.deepcopy(ai_model_entity)
                ai_model_entity_copy.entity.model = model
                ai_model_entity_copy.entity.label.en_us = model
                ai_model_entity_copy.entity.label.zh_hans = model
                return ai_model_entity_copy
        return None
