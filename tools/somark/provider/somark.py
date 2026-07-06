from typing import Any

import requests
from dify_plugin import ToolProvider


# Official SoMark API base URLs by region:
#   - somark.cn  : Mainland China
#   - somark.ai  : Taiwan (China), Hong Kong (China), Macau (China), and other overseas regions
SOMARK_OFFICIAL_BASE_URLS = (
    "https://somark.cn/api/v1",
    "https://somark.ai/api/v1",
)


class SoMarkProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate credentials.
        """
        base_url = (credentials.get("base_url") or "").strip()
        api_key = (credentials.get("api_key") or "")

        if not base_url:
            raise ValueError("Base URL is required")


        base_url = base_url.rstrip("/")

        if  not base_url.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with http:// or https://")

        if base_url in SOMARK_OFFICIAL_BASE_URLS and not api_key:
            raise ValueError("API Key is required when using the SoMark API")

        if base_url in SOMARK_OFFICIAL_BASE_URLS:
            self._validate_api_key_via_official(base_url, api_key)

    

    @staticmethod
    def _validate_api_key_via_official(base_url: str, api_key: str) -> None:
        try:
            resp = requests.post(
                f"{base_url}/usage",
                data={"api_key": api_key},
                timeout=10,
            )
        except requests.RequestException as e:
            raise ValueError(f"Failed to connect to SoMark API, please check your network: {e}") from e

        try:
            payload = resp.json()
        except ValueError:
            raise ValueError(
                f"SoMark API returned a non-JSON response (HTTP {resp.status_code})"
            )
        
        if not isinstance(payload, dict):
            raise ValueError(f"SoMark API returned an unexpected response format: {payload!r}")

        if payload.get("code") == 1107:
            raise ValueError("Invalid API Key, please check and try again")

        data = payload.get("data")

        if payload.get("code") == 0 and isinstance(data, dict) and data.get("remaining_paid_pages")==0 and data.get("remaining_free_pages_this_month")==0:
            raise ValueError("No remaining page quota, please check and try again")

        if not resp.ok:
            message = payload.get("message") or "unknown error"
            raise ValueError(f"SoMark API Key validation failed: {message}")