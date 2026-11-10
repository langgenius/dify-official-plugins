from typing import Any

import requests


class DeepSeekAPIError(ValueError):
    """A failed DeepSeek API request or invalid API response."""


class DeepSeekClient:
    BASE_URL = "https://api.deepseek.com"

    def __init__(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("api_key")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("DeepSeek API key is required.")
        self.headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            response = requests.request(
                method,
                f"{self.BASE_URL}{path}",
                headers=self.headers,
                timeout=(10, 90),
                **kwargs,
            )
        except requests.Timeout:
            raise DeepSeekAPIError(
                "DeepSeek request timed out. Please try again."
            ) from None
        except requests.RequestException:
            raise DeepSeekAPIError("Unable to connect to the DeepSeek API.") from None

        if not response.ok:
            messages = {
                400: "Invalid DeepSeek request parameters.",
                401: "Invalid DeepSeek API key.",
                402: "Insufficient DeepSeek account balance.",
                403: "DeepSeek denied access to the requested page.",
                404: "DeepSeek could not retrieve the requested page.",
                408: "DeepSeek request timed out. Please try again.",
                413: "DeepSeek request is too large.",
                429: "DeepSeek rate limit exceeded. Please try again later.",
            }
            raise DeepSeekAPIError(
                messages.get(
                    response.status_code,
                    f"DeepSeek API returned HTTP {response.status_code}.",
                )
            )
        try:
            data = response.json()
        except ValueError:
            raise DeepSeekAPIError("DeepSeek API returned invalid JSON.") from None
        if not isinstance(data, dict):
            raise DeepSeekAPIError("DeepSeek API returned an unexpected response.")
        return data

    def validate_credentials(self) -> None:
        self._request("GET", "/models")

    def search(self, parameters: dict[str, Any]) -> dict:
        data = self._request("POST", "/v1/tools/search", json=parameters)
        if not isinstance(data.get("results"), list) or any(
            not isinstance(result, dict) for result in data["results"]
        ):
            raise DeepSeekAPIError("DeepSeek Search returned an unexpected response.")
        return data

    def fetch(self, url: str) -> dict:
        data = self._request("POST", "/v1/tools/fetch", json={"url": url})
        if not all(isinstance(data.get(field), str) for field in ("title", "content")):
            raise DeepSeekAPIError("DeepSeek Fetch returned an unexpected response.")
        return data
