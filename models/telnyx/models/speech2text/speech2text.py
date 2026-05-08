from __future__ import annotations

from typing import IO, Optional

import requests
from dify_plugin import Speech2TextModel
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError

from ..common_telnyx import _CommonTelnyx


class TelnyxSpeech2TextModel(_CommonTelnyx, Speech2TextModel):
    """Telnyx audio transcription model."""

    TRANSCRIPTIONS_PATH = "/v2/ai/audio/transcriptions"

    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        filename = getattr(file, "name", "audio") or "audio"
        data = {"model": model}
        if user:
            data["user"] = user
        response = requests.post(
            self._build_url(credentials, self.TRANSCRIPTIONS_PATH),
            headers=self._get_headers(credentials, json_content=False),
            data=data,
            files={"file": (filename, file, "application/octet-stream")},
            timeout=(10, 300),
        )
        self._raise_for_response(response)
        payload = response.json()
        text = payload.get("text")
        if text is None:
            raise InvokeBadRequestError("Telnyx transcription response missing text")
        return str(text)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        # Avoid generating synthetic audio in validation; provider-level validation uses embeddings.
        if not (credentials.get("telnyx_api_key") or credentials.get("api_key")):
            raise CredentialsValidateFailedError("Telnyx API key is required")
