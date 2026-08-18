from typing import IO

from dify_plugin import Speech2TextModel
from dify_plugin.errors.model import CredentialsValidateFailedError
from openai import OpenAI

from ..common_openai import _CommonOpenAI


class OpenAISpeech2TextModel(_CommonOpenAI, Speech2TextModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        file: IO[bytes],
        user: str | None = None,
    ) -> str:
        return self._speech2text_invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            with open(self._get_demo_file_path(), "rb") as audio_file:
                self._speech2text_invoke(model, credentials, audio_file)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def _speech2text_invoke(
        self, model: str, credentials: dict, file: IO[bytes]
    ) -> str:
        client = OpenAI(**self._to_credential_kwargs(credentials))
        parameters = (
            {"chunking_strategy": "auto", "response_format": "diarized_json"}
            if model == "gpt-4o-transcribe-diarize"
            else {}
        )
        return client.audio.transcriptions.create(
            model=model,
            file=file,
            **parameters,
        ).text
