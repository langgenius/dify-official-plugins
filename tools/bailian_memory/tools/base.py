import json
from typing import Any

import requests

BASE_URL = "https://dashscope.aliyuncs.com/api/v2/apps/memory"


class BailianMemoryBaseTool:
    """Base mixin for Bailian Memory API tools."""

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
        url = f"{BASE_URL}/{path}" if path else BASE_URL
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
