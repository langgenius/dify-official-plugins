from collections.abc import Generator
from contextlib import contextmanager

import requests
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models._credentials import ENDPOINT_URL, validate_model_access


class TokenerAPIModel:
    def validate_credentials(self, model: str, credentials: dict) -> None:
        validate_model_access(credentials, model)

    @property
    def _invoke_error_mapping(self) -> dict:
        return {}

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return InvokeServerUnavailableError("Tokener.ai returned an invalid response")

    @contextmanager
    def _request(
        self, path: str, credentials: dict, *, timeout: tuple[int, int] = (10, 120), **kwargs
    ) -> Generator[requests.Response, None, None]:
        try:
            with requests.post(
                f"{ENDPOINT_URL}/{path}",
                headers={"Authorization": f"Bearer {credentials['api_key']}"},
                timeout=timeout,
                **kwargs,
            ) as response:
                status = response.status_code
                if status in {401, 403}:
                    raise InvokeAuthorizationError("Tokener.ai denied model access")
                if status == 429:
                    raise InvokeRateLimitError("Tokener.ai rate limit exceeded")
                if 400 <= status < 500:
                    raise InvokeBadRequestError(f"Tokener.ai rejected the request (HTTP {status})")
                if status != 200:
                    raise InvokeServerUnavailableError(f"Tokener.ai request failed (HTTP {status})")
                yield response
        except requests.exceptions.JSONDecodeError as ex:
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid response") from ex
        except requests.RequestException as ex:
            raise InvokeConnectionError("Unable to reach Tokener.ai") from ex

    def _post(self, path: str, credentials: dict, payload: dict) -> dict:
        with self._request(path, credentials, json=payload) as response:
            result = response.json()
        if not isinstance(result, dict):
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid response")
        return result
