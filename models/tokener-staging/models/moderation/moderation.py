from dify_plugin.entities.model import ModelPropertyKey
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.moderation_model import ModerationModel

from models._api import TokenerAPIModel


class TokenerModerationModel(TokenerAPIModel, ModerationModel):
    def _invoke(self, model: str, credentials: dict, text: str, user: str | None = None) -> bool:
        schema = self.get_model_schema(model, credentials)
        properties = schema.model_properties if schema else {}
        limit = properties.get(ModelPropertyKey.MAX_CHARACTERS_PER_CHUNK, 2000)
        batch_size = properties.get(ModelPropertyKey.MAX_CHUNKS, 1)
        chunks = [text[start : start + limit] for start in range(0, len(text), limit)]
        for offset in range(0, len(chunks), batch_size):
            result = self._post(
                "moderations",
                credentials,
                {"model": model, "input": chunks[offset : offset + batch_size]},
            )
            if any(item["flagged"] for item in result["results"]):
                return True
        return False

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self._post("moderations", credentials, {"model": model, "input": ["ping"]})
        except Exception as error:
            raise CredentialsValidateFailedError(
                "Tokener.ai moderation validation failed"
            ) from error
