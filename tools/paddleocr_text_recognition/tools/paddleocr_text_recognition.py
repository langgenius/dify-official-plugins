from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class PaddleocrTextRecognitionTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Invoke the PaddleOCR API to recognize the text in the image."""
        try:
            access_token = self.runtime.credentials["aistudio_access_token"]
        except KeyError as e:
            raise RuntimeError(
                "AI Studio Access Token is not configured or invalid. Please provide it in the plugin settings."
            ) from e

        if "file" not in tool_parameters:
            raise RuntimeError("File is not provided.")
        params: dict[str, Any] = {}
        params["file"] = tool_parameters["file"]
        for optional_param_name in [
            "fileType",
            "useDocOrientationClassify",
            "useDocUnwarping",
            "useTextlineOrientation",
            "textDetLimitSideLen",
            "textDetLimitType",
            "textDetThresh",
            "textDetBoxThresh",
            "textDetUnclipRatio",
            "textRecScoreThresh",
            "returnWordBox",
            "visualize",
        ]:
            if optional_param_name in tool_parameters:
                params[optional_param_name] = tool_parameters[optional_param_name]

        try:
            resp = requests.post(
                self.runtime.credentials["api_url"],
                headers={"Authorization": f"Bearer {access_token}"},
                json=params,
            )
            resp.raise_for_status()
            yield self.create_json_message(resp.json())
        except requests.exceptions.JSONDecodeError as e:
            raise RuntimeError(
                f"Failed to decode JSON response from PaddleOCR API: {resp.text}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"PaddleOCR API request failed: {e}") from e
