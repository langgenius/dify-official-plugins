import requests
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

REQUEST_TIMEOUT = (10, 300)


def build_headers(credentials: dict) -> dict[str, str]:
    api_key = credentials.get("api_key")
    if not api_key:
        raise InvokeAuthorizationError("API key is required.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://dify.ai/",
        "X-Title": "Dify",
    }


def raise_for_status(response: requests.Response, operation: str) -> None:
    """Map a non-2xx OpenRouter response to the matching Dify invoke error.

    Audio endpoints return JSON error bodies on failure, whose message (for example
    an unknown voice) is the only actionable detail, so it is kept in the error.
    """
    if response.ok:
        return
    response.close()
    status_code = response.status_code
    detail = ""
    try:
        error = response.json().get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
    except (ValueError, AttributeError):
        pass
    message = f"OpenRouter {operation} request failed with status {status_code}."
    if detail:
        message = f"{message} {detail[:500]}"

    if status_code in (401, 403):
        raise InvokeAuthorizationError(message)
    if status_code == 429:
        raise InvokeRateLimitError(message)
    if status_code >= 500:
        raise InvokeServerUnavailableError(message)
    raise InvokeBadRequestError(message)


def post(url: str, operation: str, **kwargs) -> requests.Response:
    try:
        response = requests.post(url, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.exceptions.Timeout as ex:
        raise InvokeConnectionError(f"OpenRouter {operation} request timed out.") from ex
    except requests.exceptions.ConnectionError as ex:
        raise InvokeConnectionError("Unable to connect to OpenRouter.") from ex
    except requests.exceptions.RequestException as ex:
        raise InvokeServerUnavailableError(str(ex)) from ex
    raise_for_status(response, operation)
    return response
