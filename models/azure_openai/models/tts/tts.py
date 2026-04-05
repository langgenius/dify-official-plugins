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
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str
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
            client = self._create_client(credentials)
            max_length = 3500
            if len(content_text) > max_length:
                sentences = self._split_text_into_sentences(
                    content_text, max_length=max_length
                )
                executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(3, len(sentences))
                )
                futures = [
                    executor.submit(
                        client.audio.speech.with_streaming_response.create,
                        model=model,
                        response_format=self._get_model_audio_type(model, credentials),
                        input=sentences[i],
                        voice=voice,
                    )
                    for i in range(len(sentences))
                ]
                for future in futures:
                    yield from future.result().__enter__().iter_bytes(1024)
            else:
                response = client.audio.speech.with_streaming_response.create(
                    model=model,
                    voice=voice,
                    response_format=self._get_model_audio_type(model, credentials),
                    input=content_text.strip(),
                )
                yield from response.__enter__().iter_bytes(1024)
        except Exception as ex:
            raise InvokeBadRequestError(str(ex))

    def _process_sentence(self, sentence: str, model: str, voice, credentials: dict):
        """
        _tts_invoke openai text2speech model api

        :param model: model name
        :param credentials: model credentials
        :param voice: model timbre
        :param sentence: text content to be translated
        :return: text translated to audio file
        """
        client = self._create_client(credentials)
        response = client.audio.speech.create(
            model=model, voice=voice, input=sentence.strip(),
            response_format=self._get_model_audio_type(model, credentials),
        )
        if isinstance(response.read(), bytes):
            return response.read()

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
                ai_model_entity_copy.entity.label.en_US = model
                ai_model_entity_copy.entity.label.zh_Hans = model
                return ai_model_entity_copy
        return None
