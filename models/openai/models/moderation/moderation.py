from dify_plugin import ModerationModel
from dify_plugin.entities.model import ModelPropertyKey
from dify_plugin.errors.model import CredentialsValidateFailedError
from openai import OpenAI
from openai.types import ModerationCreateResponse

from ..common_openai import _CommonOpenAI


class OpenAIModerationModel(_CommonOpenAI, ModerationModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        text: str,
        user: str | None = None,
    ) -> bool:
        client = OpenAI(**self._to_credential_kwargs(credentials))
        length = self._get_max_characters_per_chunk(model, credentials)
        text_chunks = [
            text[start : start + length] for start in range(0, len(text), length)
        ]

        batch_size = self._get_max_chunks(model, credentials)
        for start in range(0, len(text_chunks), batch_size):
            response = self._moderation_invoke(
                model=model,
                client=client,
                texts=text_chunks[start : start + batch_size],
            )
            if any(result.flagged for result in response.results):
                return True

        return False

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            self._moderation_invoke(
                model=model,
                client=OpenAI(**self._to_credential_kwargs(credentials)),
                texts=["ping"],
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def _moderation_invoke(
        self, model: str, client: OpenAI, texts: list[str]
    ) -> ModerationCreateResponse:
        return client.moderations.create(model=model, input=texts)

    def _get_max_characters_per_chunk(self, model: str, credentials: dict) -> int:
        model_schema = self.get_model_schema(model, credentials)
        if (
            model_schema
            and ModelPropertyKey.MAX_CHARACTERS_PER_CHUNK
            in model_schema.model_properties
        ):
            return model_schema.model_properties[
                ModelPropertyKey.MAX_CHARACTERS_PER_CHUNK
            ]
        return 2000

    def _get_max_chunks(self, model: str, credentials: dict) -> int:
        model_schema = self.get_model_schema(model, credentials)
        if (
            model_schema
            and ModelPropertyKey.MAX_CHUNKS in model_schema.model_properties
        ):
            return model_schema.model_properties[ModelPropertyKey.MAX_CHUNKS]
        return 1
