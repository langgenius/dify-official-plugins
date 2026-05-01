from typing import Any

import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

# A tiny POST that the API rejects with 400 ("model not supported") when the
# token is valid, and with 401 when it isn't. No image is generated, no quota
# is consumed.
PROBE_URL = "https://aistudio.baidu.com/llm/lmapi/v3/images/generations"
PROBE_PAYLOAD = {"model": "__validate__", "prompt": "ping", "n": 1}


class ErnieImageProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        token = (credentials.get("access_token") or "").strip()
        if not token:
            raise ToolProviderCredentialValidationError("Access token is required")

        try:
            response = requests.post(
                PROBE_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=PROBE_PAYLOAD,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise ToolProviderCredentialValidationError(f"Network error: {exc}") from exc

        # 200 = unexpected acceptance, 400 = "model not supported" (token is valid).
        # Anything else (401/403/429/5xx/...) means the token cannot be used.
        if response.status_code == 401:
            raise ToolProviderCredentialValidationError("Invalid AI Studio access token")
        if response.status_code not in (200, 400):
            kind = "unavailable" if response.status_code >= 500 else "rejected the probe"
            raise ToolProviderCredentialValidationError(
                f"AI Studio {kind} (HTTP {response.status_code})"
            )
