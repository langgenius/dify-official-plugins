from typing import IO, Optional
from dify_plugin import OAICompatSpeech2TextModel
from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelType


class FunASRSpeech2TextModel(OAICompatSpeech2TextModel):
    """FunASR speech-to-text via OpenAI-compatible API."""

    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        compat = self._compat_credentials(credentials)
        return super()._invoke(model, compat, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        compat = self._compat_credentials(credentials)
        super().validate_credentials(model, compat)

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={},
            parameter_rules=[],
        )

    @classmethod
    def _compat_credentials(cls, credentials: dict) -> dict:
        credentials = credentials.copy()
        base = credentials["endpoint_url"].rstrip("/").removesuffix("/v1")
        credentials["endpoint_url"] = f"{base}/v1"
        credentials.setdefault("api_key", "no-key")
        return credentials
