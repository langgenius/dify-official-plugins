from typing import IO

from dify_plugin import Speech2TextModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeError,
    InvokeServerUnavailableError,
)

from models._api import TokenerAPIModel


class TokenerSpeech2TextModel(TokenerAPIModel, Speech2TextModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        file: IO[bytes],
        user: str | None = None,
    ) -> str:
        payload = {"model": model}
        if model == "gpt-4o-transcribe-diarize":
            payload |= {"chunking_strategy": "auto", "response_format": "diarized_json"}
        with (
            file,
            self._request(
                "audio/transcriptions",
                credentials,
                data=payload,
                files=[("file", file)],
                timeout=(10, 300),
            ) as response,
        ):
            result = response.json()
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid transcription")
        return result["text"]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            with open(self._get_demo_file_path(), "rb") as audio_file:
                self.invoke(model, credentials, audio_file)
        except (InvokeError, OSError) as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex
