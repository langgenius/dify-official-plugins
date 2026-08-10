import json
from typing import Any

import requests

MEMORY_API_PATH = "/api/v2/apps/memory"
DASHSCOPE_CN_BASE_URL = "https://dashscope.aliyuncs.com"
DASHSCOPE_INTL_BASE_URL = "https://dashscope-intl.aliyuncs.com"


class BailianMemoryBaseTool:
    """Base mixin for Bailian Memory API tools."""

    def _get_base_url(self) -> str:
        """Memory API base for the configured endpoint. Defaults to the China
        (Beijing) endpoint so existing installations keep their exact current
        behavior; Model Studio API keys are region-specific, so international
        (Singapore) keys need dashscope-intl."""
        creds = self.runtime.credentials
        if creds.get("use_international_endpoint", "false") == "true":
            return DASHSCOPE_INTL_BASE_URL + MEMORY_API_PATH
        return DASHSCOPE_CN_BASE_URL + MEMORY_API_PATH

    def _get_headers(self) -> dict[str, str]:
        api_key = self.runtime.credentials["dashscope_api_key"]
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = self._get_base_url()
        url = f"{base_url}/{path}" if path else base_url
        response = requests.request(
            method,
            url,
            headers=self._get_headers(),
            json=json_body,
            params=params,
            timeout=60,
        )
        if not response.ok:
            try:
                error_detail = response.json()
            except Exception:
                error_detail = response.text
            raise Exception(
                f"API request failed ({response.status_code}): "
                f"{json.dumps(error_detail, ensure_ascii=False) if isinstance(error_detail, dict) else error_detail}"
            )
        return response.json()

    def _format_response(self, result: dict[str, Any]) -> str:
        return json.dumps(result, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_json_param(value: str, param_name: str) -> Any:
        """Parse a JSON string parameter, raising ValueError with a clear message on failure."""
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format for '{param_name}' parameter.")
