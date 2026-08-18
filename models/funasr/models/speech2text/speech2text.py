from typing import IO, Optional

import httpx
from dify_plugin import OAICompatSpeech2TextModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
)
from dify_plugin.errors.model import CredentialsValidateFailedError


class FunASRSpeech2TextModel(OAICompatSpeech2TextModel):
    """FunASR speech-to-text via OpenAI-compatible API."""

    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        compat = self._compat_credentials(credentials)
        return super()._invoke(model, compat, file, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        compat = self._compat_credentials(credentials)
        try:
            super().validate_credentials(model, compat)
        except CredentialsValidateFailedError:
            # Some FunASR OpenAI-compatible servers only implement
            # /v1/audio/transcriptions and don't expose /v1/models, which the
            # base validator relies on. Fall back to a direct reachability check.
            self._check_endpoint_reachable(compat)

    @staticmethod
    def _check_endpoint_reachable(credentials: dict) -> None:
        endpoint = credentials["endpoint_url"].rstrip("/")
        try:
            resp = httpx.get(endpoint, timeout=10)
        except Exception as e:
            raise CredentialsValidateFailedError(f"Could not reach FunASR endpoint '{endpoint}': {e}") from e
        if resp.status_code >= 500:
            raise CredentialsValidateFailedError(
                f"FunASR endpoint '{endpoint}' returned server error {resp.status_code}."
            )

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={
                ModelPropertyKey.FILE_UPLOAD_LIMIT: 25,
                ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS: "flac,mp3,mp4,mpeg,mpga,m4a,ogg,wav,webm",
            },
            parameter_rules=[],
        )

    @classmethod
    def _compat_credentials(cls, credentials: dict) -> dict:
        credentials = credentials.copy()
        endpoint_url = credentials.get("endpoint_url")
        if not endpoint_url:
            raise CredentialsValidateFailedError("'endpoint_url' is required for the FunASR provider.")
        base = endpoint_url.rstrip("/").removesuffix("/v1")
        credentials["endpoint_url"] = f"{base}/v1"
        if not credentials.get("api_key"):
            credentials["api_key"] = "no-key"
        return credentials
