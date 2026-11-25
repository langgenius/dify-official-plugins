from pathlib import Path
from typing import IO
from urllib.parse import urlparse

import httpx
from dify_plugin import Speech2TextModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

DEFAULT_ENDPOINT_URL = "https://speech-api.oruk.ai/v1"
MAX_AUDIO_BYTES = 30 * 1024 * 1024
SUPPORTED_EXTENSIONS = "flac,mp3,m4a,ogg,wav,webm"
_EXTENSION_MIME_TYPES: dict[str, str] = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}
_REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)
_VALIDATE_TIMEOUT = httpx.Timeout(connect=10.0, read=10.0, write=10.0, pool=10.0)


def normalize_endpoint_url(endpoint_url: str | None) -> str:
    """Normalize an Oruk or OpenAI-compatible base URL so it ends with `/v1`."""
    raw = (endpoint_url or "").strip()
    if not raw:
        return DEFAULT_ENDPOINT_URL

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise CredentialsValidateFailedError(
            "Endpoint URL must be a valid http:// or https:// URL."
        )

    cleaned = raw.rstrip("/").removesuffix("/audio/transcriptions")
    if cleaned.endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"


def is_hosted_oruk_endpoint(endpoint_url: str) -> bool:
    """Return True when the normalized endpoint targets Oruk's hosted Speech API."""
    host = (urlparse(endpoint_url).hostname or "").lower()
    return host == "oruk.ai" or host.endswith(".oruk.ai")


def detect_audio_upload_meta(audio_bytes: bytes, file_name: str | None = None) -> tuple[str, str]:
    """Infer an upload `(filename, content_type)` from filename or container magic bytes.

    Dify may pass an anonymous temporary file object without a media extension.
    Detecting magic bytes ensures Oruk's multipart `/v1/audio/transcriptions` endpoint
    and OpenAI-compatible self-hosted servers receive a valid filename and MIME type.
    """
    if file_name:
        ext = Path(file_name).suffix.lower()
        if ext in _EXTENSION_MIME_TYPES:
            return (Path(file_name).name, _EXTENSION_MIME_TYPES[ext])

    header = audio_bytes[:16]
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return ("audio.wav", "audio/wav")
    if header.startswith(b"fLaC"):
        return ("audio.flac", "audio/flac")
    if header.startswith(b"OggS"):
        return ("audio.ogg", "audio/ogg")
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return ("audio.m4a", "audio/mp4")
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return ("audio.webm", "audio/webm")
    return ("audio.mp3", "audio/mpeg")


def _extract_error_message(response: httpx.Response) -> str:
    """Extract a concise, sanitized error detail from an upstream HTTP error response."""
    detail = ""
    try:
        body = response.json()
    except ValueError:
        body = None

    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            code = err.get("code")
            if isinstance(msg, str) and msg.strip():
                detail = f"{code}: {msg.strip()}" if isinstance(code, str) and code else msg.strip()
        elif isinstance(err, str) and err.strip():
            detail = err.strip()
        elif isinstance(body.get("detail"), str) and body["detail"].strip():
            detail = body["detail"].strip()

    if not detail:
        text = (response.text or "").strip()
        detail = text[:200] if text else f"HTTP {response.status_code}"
    elif len(detail) > 200:
        detail = detail[:200]
    return detail


def _build_headers(api_key: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


class OrukSpeech2TextModel(Speech2TextModel):
    """Speech-to-text model backed by Oruk Fourier-2B via OpenAI-compatible REST."""

    def _invoke(
        self,
        model: str,
        credentials: dict,
        file: IO[bytes],
        user: str | None = None,
    ) -> str:
        del user
        endpoint_url, api_key = self._resolve_credentials(credentials, for_invoke=True)

        audio_bytes = file.read()
        if not audio_bytes:
            raise InvokeBadRequestError("Audio file must not be empty.")
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise InvokeBadRequestError(
                "Audio file exceeds the 30 MiB upload limit for Oruk speech-to-text."
            )

        raw_name = getattr(file, "name", None)
        file_name = raw_name if isinstance(raw_name, str) else None
        upload_name, content_type = detect_audio_upload_meta(audio_bytes, file_name=file_name)

        url = f"{endpoint_url}/audio/transcriptions"
        try:
            response = httpx.post(
                url,
                headers=_build_headers(api_key),
                data={"model": model, "response_format": "json"},
                files={"file": (upload_name, audio_bytes, content_type)},
                timeout=_REQUEST_TIMEOUT,
            )
        except httpx.TimeoutException as exc:
            raise InvokeConnectionError(
                f"Timed out waiting for Oruk transcription endpoint '{url}'."
            ) from exc
        except httpx.RequestError as exc:
            raise InvokeConnectionError(
                f"Could not reach Oruk transcription endpoint '{url}': {exc}"
            ) from exc

        self._raise_for_invoke_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise InvokeServerUnavailableError(
                "Oruk returned a non-JSON transcription response."
            ) from exc

        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise InvokeServerUnavailableError(
                "Oruk returned a transcription response without a text field."
            )
        return text

    def validate_credentials(self, model: str, credentials: dict) -> None:
        del model
        endpoint_url, api_key = self._resolve_credentials(credentials, for_invoke=False)
        headers = _build_headers(api_key)
        models_url = f"{endpoint_url}/models"

        try:
            response = httpx.get(models_url, headers=headers, timeout=_VALIDATE_TIMEOUT)
        except httpx.RequestError as exc:
            raise CredentialsValidateFailedError(
                f"Could not reach Oruk endpoint '{models_url}': {exc}"
            ) from exc

        if response.status_code == 200:
            return

        if response.status_code in (401, 403):
            detail = _extract_error_message(response)
            raise CredentialsValidateFailedError(
                f"Authentication failed for Oruk endpoint ({response.status_code}): {detail}"
            )

        if response.status_code >= 500:
            raise CredentialsValidateFailedError(
                f"Oruk endpoint returned server error {response.status_code}."
            )

        # Custom self-hosted servers (e.g. minimal OpenAI-compatible wrappers) may only
        # serve /v1/audio/transcriptions without /v1/models. Hosted Oruk always serves /v1/models.
        if not is_hosted_oruk_endpoint(endpoint_url) and response.status_code in (404, 405):
            self._check_custom_endpoint_reachable(endpoint_url, headers)
            return

        detail = _extract_error_message(response)
        raise CredentialsValidateFailedError(
            f"Oruk endpoint validation failed ({response.status_code}): {detail}"
        )

    @staticmethod
    def _check_custom_endpoint_reachable(endpoint_url: str, headers: dict[str, str]) -> None:
        base_url = endpoint_url.removesuffix("/v1")
        try:
            resp = httpx.get(base_url, headers=headers, timeout=_VALIDATE_TIMEOUT)
        except httpx.RequestError as exc:
            raise CredentialsValidateFailedError(
                f"Could not reach self-hosted endpoint '{base_url}': {exc}"
            ) from exc

        if resp.status_code in (401, 403):
            detail = _extract_error_message(resp)
            raise CredentialsValidateFailedError(
                f"Authentication failed for self-hosted endpoint ({resp.status_code}): {detail}"
            )
        if resp.status_code >= 500:
            raise CredentialsValidateFailedError(
                f"Self-hosted endpoint '{base_url}' returned server error {resp.status_code}."
            )

    @staticmethod
    def _resolve_credentials(credentials: dict, *, for_invoke: bool) -> tuple[str, str]:
        try:
            endpoint_url = normalize_endpoint_url(credentials.get("endpoint_url"))
        except CredentialsValidateFailedError as exc:
            if for_invoke:
                raise InvokeBadRequestError(str(exc)) from exc
            raise

        api_key = str(credentials.get("api_key") or "").strip()
        if is_hosted_oruk_endpoint(endpoint_url) and not api_key:
            msg = f"An Oruk API key is required for {DEFAULT_ENDPOINT_URL}."
            if for_invoke:
                raise InvokeAuthorizationError(msg)
            raise CredentialsValidateFailedError(msg)
        return endpoint_url, api_key

    @staticmethod
    def _raise_for_invoke_status(response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        detail = _extract_error_message(response)
        if status in (401, 403):
            raise InvokeAuthorizationError(f"Oruk authentication failed ({status}): {detail}")
        if status == 429:
            raise InvokeRateLimitError(f"Oruk rate limit exceeded ({status}): {detail}")
        if status in (400, 413, 415, 422):
            raise InvokeBadRequestError(f"Oruk rejected the transcription request ({status}): {detail}")
        if status >= 500:
            raise InvokeServerUnavailableError(f"Oruk service unavailable ({status}): {detail}")
        raise InvokeBadRequestError(f"Oruk request failed ({status}): {detail}")

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity | None:
        del credentials
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={
                ModelPropertyKey.FILE_UPLOAD_LIMIT: 30,
                ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS: SUPPORTED_EXTENSIONS,
            },
            parameter_rules=[],
        )

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {}
