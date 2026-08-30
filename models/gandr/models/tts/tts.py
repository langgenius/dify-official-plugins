from collections.abc import Generator
from typing import Optional

import httpx

from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
)


class GandrText2SpeechModel(TTSModel):
    """
    Model class for Gandr text to speech model.
    """

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        """
        Invoke text to speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param voice: voice to speak with
        :param content_text: text content to be synthesized
        :param user: unique user id
        :return: generator yielding audio bytes
        """
        return self._tts_invoke(
            model=model,
            credentials=credentials,
            content_text=content_text,
            voice=voice,
        )

    def validate_credentials(
        self, model: str, credentials: dict, user: Optional[str] = None
    ) -> None:
        """
        Validate credentials with a small synthesis request

        :param model: model name
        :param credentials: model credentials
        :param user: unique user id
        """
        try:
            voice = self._get_model_default_voice(model, credentials) or "gandr-ava"
            list(self._tts_invoke(model=model, credentials=credentials, content_text="Hello.", voice=voice))
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> Generator[bytes, None, None]:
        """
        Call the Gandr speech endpoint and yield audio bytes

        The endpoint returns the whole response for each request, so texts longer
        than the model word limit are split into sentences first.

        :param model: model name
        :param credentials: model credentials
        :param content_text: text content to be synthesized
        :param voice: voice to speak with
        :return: generator yielding audio bytes
        """
        api_key = credentials.get("api_key")
        word_limit = self._get_model_word_limit(model, credentials) or 2000
        sentences = self._split_text_into_sentences(content_text, max_length=word_limit)

        for sentence in sentences:
            try:
                response = httpx.post(
                    "https://tts.gandr.ai/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "input": sentence.strip(),
                        "voice": voice,
                        "response_format": "mp3",
                    },
                    timeout=120,
                )
                response.raise_for_status()
            except httpx.HTTPError as ex:
                raise InvokeBadRequestError(str(ex)) from ex
            yield response.content

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
                httpx.HTTPError,
            ],
        }
