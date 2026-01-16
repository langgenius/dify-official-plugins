from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import (
    convert_file_type,
    get_markdown_from_result,
    make_paddleocr_api_request,
    process_images_from_result,
)


class DocumentParsingTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Invoke the PaddleOCR API to parse the document images."""
        if "aistudio_access_token" not in self.runtime.credentials:
            raise RuntimeError(
                "The AI Studio access token is not configured or invalid. Please provide it in the plugin settings."
            )
        access_token = self.runtime.credentials["aistudio_access_token"]

        if "document_parsing_api_url" not in self.runtime.credentials:
            raise RuntimeError(
                "The document parsing API URL is not configured or invalid. Please provide it in the plugin settings."
            )
        api_url = self.runtime.credentials["document_parsing_api_url"]

        if "file" not in tool_parameters:
            raise RuntimeError("File is not provided.")

        params: dict[str, Any] = {}
        params["file"] = tool_parameters["file"]
        for optional_param_name in [
            "fileType",
            "useDocOrientationClassify",
            "useDocUnwarping",
            "useTextlineOrientation",
            "useSealRecognition",
            "useTableRecognition",
            "useFormulaRecognition",
            "useChartRecognition",
            "useRegionDetection",
            "layoutThreshold",
            "layoutNms",
            "layoutUnclipRatio",
            "layoutMergeBboxesMode",
            "textDetLimitSideLen",
            "textDetLimitType",
            "textDetThresh",
            "textDetBoxThresh",
            "textDetUnclipRatio",
            "textRecScoreThresh",
            "sealDetLimitSideLen",
            "sealDetLimitType",
            "sealDetThresh",
            "sealDetBoxThresh",
            "sealDetUnclipRatio",
            "sealRecScoreThresh",
            "useWiredTableCellsTransToHtml",
            "useWirelessTableCellsTransToHtml",
            "useTableOrientationClassify",
            "useOcrResultsWithTableCells",
            "useE2eWiredTableRecModel",
            "useE2eWirelessTableRecModel",
            "visualize",
        ]:
            if optional_param_name in tool_parameters:
                params[optional_param_name] = tool_parameters[optional_param_name]

        # Convert fileType parameter
        if "fileType" in params:
            params["fileType"] = convert_file_type(params["fileType"])

        result = make_paddleocr_api_request(api_url, params, access_token)

        images, image_path_map, failed_images, blob_messages = (
            process_images_from_result(result, self)
        )

        markdown = get_markdown_from_result(result, image_path_map, failed_images)

        for blob_data, blob_meta in blob_messages:
            yield self.create_blob_message(blob_data, meta=blob_meta)

        yield self.create_variable_message("images", images)
        yield self.create_text_message(markdown)
        yield self.create_json_message(result)
