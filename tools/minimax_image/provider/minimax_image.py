from typing import Any

import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils import base_url

# MiniMax has no dedicated "check this key" endpoint, but listing files is free and requires the
# same bearer token as the image endpoints, so it validates the key against the selected
# regional endpoint without starting a billable image job.
VALIDATION_PATH = "/v1/files/list"
VALIDATION_TIMEOUT = (10, 30)


class MiniMaxImageProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = str(credentials.get("api_key") or "").strip()
        if not api_key:
            raise ToolProviderCredentialValidationError("MiniMax API key is required")

        endpoint = credentials.get("api_endpoint") or "international"
        url = base_url({"api_endpoint": endpoint}) + VALIDATION_PATH
        try:
            response = requests.get(
                url,
                params={"purpose": "image_generation_input"},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=VALIDATION_TIMEOUT,
            )
            body = response.json()
        except Exception as exc:
            raise ToolProviderCredentialValidationError(
                f"Could not reach the MiniMax {endpoint} endpoint to validate the API key: {exc}"
            ) from exc

        base_resp = body.get("base_resp") if isinstance(body, dict) else None
        status_code = base_resp.get("status_code") if isinstance(base_resp, dict) else None
        if response.status_code != 200 or status_code not in (0, None):
            message = base_resp.get("status_msg") if isinstance(base_resp, dict) else None
            raise ToolProviderCredentialValidationError(
                f"MiniMax rejected the API key for the {endpoint} endpoint: "
                f"{message or response.text}"
            )
