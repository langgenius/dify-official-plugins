from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import make_paddleocr_api_request, normalize_file_input


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

        file_payload, file_type = normalize_file_input(
            tool_parameters.get("file"), tool_parameters.get("fileType")
        )

        params: dict[str, Any] = {"file": file_payload}
        if file_type is not None:
            params["fileType"] = file_type
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
            if optional_param_name in tool_parameters and optional_param_name != "fileType":
                params[optional_param_name] = tool_parameters[optional_param_name]

        result = make_paddleocr_api_request(api_url, params, access_token)

        all_text = []
        for item in result.get("result", {}).get("ocrResults", []):
            text_list = item.get("prunedResult", {}).get("rec_texts")
            if text_list is not None:
                all_text.append("\n".join(text_list))
        yield self.create_text_message("\n\n".join(all_text))
        yield self.create_json_message(result)
