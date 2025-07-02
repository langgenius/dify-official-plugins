from typing import Optional, IO
from dify_plugin import OAICompatSpeech2TextModel
from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelType

class GPUStackSpeechToTextModel(OAICompatSpeech2TextModel):
    """
    Model class for GPUStack Speech to text model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        file: IO[bytes],
        user: Optional[str] = None,
    ) -> str:
        model = model.strip()
        compatible_credentials = self._get_compatible_credentials(credentials)
        return super()._invoke(model, compatible_credentials,  file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        """
        compatible_credentials = self._get_compatible_credentials(credentials)
        super().validate_credentials(model, compatible_credentials)

    def _get_compatible_credentials(self, credentials: dict) -> dict:
        credentials = credentials.copy()
        base_url = credentials["endpoint_url"].rstrip("/").removesuffix("/v1").removesuffix("/v1-openai")
        credentials["endpoint_url"] = f"{base_url}/v1"
        return credentials

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        Used to define customizable model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={},
            parameter_rules=[],
        )
        return entity
