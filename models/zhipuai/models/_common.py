import httpx
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from zai.core import APIResponseError, APIStatusError
from zai.core._errors import APIConnectionError


class _CommonZhipuaiAI:
    def _to_credential_kwargs(self, credentials: dict) -> dict:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        credentials_kwargs = {
            "api_key": credentials["api_key"]
            if "api_key" in credentials
            else credentials.get("zhipuai_api_key"),
        }

        if "base_url" in credentials:
            credentials_kwargs["base_url"] = credentials["base_url"]
        elif "zhipuai_base_url" in credentials:
            credentials_kwargs["base_url"] = credentials["zhipuai_base_url"]

        return credentials_kwargs

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
            InvokeConnectionError: [APIConnectionError, httpx.RequestError],
        }

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        error_type: type[InvokeError] = InvokeBadRequestError
        if isinstance(error, APIStatusError):
            # str(APIStatusError) includes the full HTTP response body.
            message = f"ZHIPU AI API request failed (HTTP {error.status_code})."
            try:
                body = error.response.json()
            except ValueError:
                body = None

            if error.status_code == 429:
                error_type = InvokeRateLimitError
            elif error.status_code in (401, 403):
                error_type = InvokeAuthorizationError
            elif error.status_code >= 500:
                error_type = InvokeServerUnavailableError
        elif isinstance(error, APIResponseError) and not isinstance(
            error, APIConnectionError
        ):
            # Streaming errors keep the provider message in json_data.
            body = error.json_data
            message = str(error)
        else:
            return super()._transform_invoke_error(error)

        if isinstance(body, dict):
            body = body.get("error", body)
            if isinstance(body, dict):
                provider_message = body.get("message")
                if isinstance(provider_message, str) and provider_message:
                    message = provider_message

        return error_type(f"[zhipuai] {message}")
