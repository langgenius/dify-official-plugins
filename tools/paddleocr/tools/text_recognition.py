from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import convert_file_type, make_paddleocr_api_request


class TextRecognitionTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Invoke the PaddleOCR API to recognize the text in the image."""
        if "aistudio_access_token" not in self.runtime.credentials:
            raise RuntimeError(
                "The AI Studio access token is not configured or invalid. Please provide it in the plugin settings."
            )
        access_token = self.runtime.credentials["aistudio_access_token"]

        if "text_recognition_api_url" not in self.runtime.credentials:
            raise RuntimeError(
                "The text recognition API URL is not configured or invalid. Please provide it in the plugin settings."
            )
        api_url = self.runtime.credentials["text_recognition_api_url"]

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

        # Convert fileType parameter
        if "fileType" in params:
            params["fileType"] = convert_file_type(params["fileType"])

        result = make_paddleocr_api_request(api_url, params, access_token)

        all_text = []
        for item in result.get("result", {}).get("ocrResults", []):
            text_list = item.get("prunedResult", {}).get("rec_texts")
            if text_list is not None:
                all_text.append("\n".join(text_list))
        yield self.create_text_message("\n\n".join(all_text))
        yield self.create_json_message(result)
