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

    def _post(self, path: str, credentials: dict, payload: dict) -> dict:
        try:
            with requests.post(
                f"{ENDPOINT_URL}/{path}",
                headers={"Authorization": f"Bearer {credentials['api_key']}"},
                json=payload,
                timeout=(10, 120),
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
                result = response.json()
        except requests.exceptions.JSONDecodeError as ex:
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid response") from ex
        except requests.RequestException as ex:
            raise InvokeConnectionError("Unable to reach Tokener.ai") from ex
        if not isinstance(result, dict):
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid response")
        return result
