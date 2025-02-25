from collections.abc import Generator
from typing import Any

import httpx

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from provider.endpoints import AGENTQL_HOST_URL, QUERY_DATA_ENDPOINT
from provider.messages import UNAUTHORIZED_ERROR_MESSAGE

class ExtractWebDataTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        url = tool_parameters["url"]
        query = tool_parameters.get("query", None)
        prompt = tool_parameters.get("prompt", None)
        
        timeout = tool_parameters["timeout"]

        metadata = {}
        metadata["experimental_stealth_mode_enabled"] = tool_parameters["stealth_mode"]

        params = {}
        params["mode"] = tool_parameters["mode"]
        params["wait_for"] = tool_parameters["wait_for"]
        params["is_scroll_to_bottom_enabled"] = tool_parameters["scroll_to_bottom"]
        params["is_screenshot_enabled"] = tool_parameters["enable_screenshot"]

        endpoint = f"{AGENTQL_HOST_URL}/{QUERY_DATA_ENDPOINT}"
        headers = {
            "X-API-Key": self.runtime.credentials["api_key"],
            "Content-Type": "application/json",
            "X-TF-Request-Origin": "dify",
        }

        payload = {
            "url": url,
            "query": query,
            "prompt": prompt,
            "params": params,
            "metadata": metadata
        }

        try:
            response = httpx.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            response = e.response
            if response.status_code == httpx.codes.UNAUTHORIZED:
                raise ValueError(UNAUTHORIZED_ERROR_MESSAGE) from e
            else:
                msg = response.text
                try:
                    error_json = response.json()
                    msg = (
                        error_json["error_info"]
                        if "error_info" in error_json
                        else str(error_json)
                    )
                except (ValueError, TypeError):
                    msg = f"HTTP {e}."
                raise ValueError(msg) from e
        else:
            json = response.json()
            yield self.create_json_message(json)
