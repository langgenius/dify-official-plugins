import copy
from typing import IO, Optional
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.speech2text_model import Speech2TextModel
from ..common import _CommonAzureOpenAI
from ..constants import SPEECH2TEXT_BASE_MODELS, AzureBaseModel

class AzureOpenAISpeech2TextModel(_CommonAzureOpenAI, Speech2TextModel):
    """
    Model class for OpenAI Speech to text model.
    """

    def _invoke(
        self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None
    ) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        return self._speech2text_invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            audio_file_path = self._get_demo_file_path()
            with open(audio_file_path, "rb") as audio_file:
                self._speech2text_invoke(model, credentials, audio_file)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _speech2text_invoke(
        self, model: str, credentials: dict, file: IO[bytes]
    ) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :return: text for given audio file
        """
        client = self._create_client(credentials)
        base_model_name = self._get_base_model_name(credentials)
        ai_model_entity = self._get_ai_model_entity(base_model_name, model)
        extra_params = ai_model_entity.extra_invoke_params if ai_model_entity else {}
        response = client.audio.transcriptions.create(model=model, file=file, **extra_params)
        return response.text

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        ai_model_entity = self._get_ai_model_entity(
            credentials["base_model_name"], model
        )
        return ai_model_entity.entity

    @staticmethod
    def _get_ai_model_entity(base_model_name: str, model: str) -> AzureBaseModel:
        for ai_model_entity in SPEECH2TEXT_BASE_MODELS:
            if ai_model_entity.base_model_name == base_model_name:
                ai_model_entity_copy = copy.deepcopy(ai_model_entity)
                ai_model_entity_copy.entity.model = model
                ai_model_entity_copy.entity.label.en_US = model
                ai_model_entity_copy.entity.label.zh_Hans = model
                return ai_model_entity_copy
        return None

    def _get_base_model_name(self, credentials: dict) -> str:
        base_model_name = credentials.get("base_model_name")
        if not base_model_name:
            raise ValueError("Base Model Name is required")
        return base_model_name
