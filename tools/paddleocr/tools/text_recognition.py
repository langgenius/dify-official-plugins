from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import (
    build_ocr_options,
    call_paddleocr_api,
    cleanup_temp_file,
    get_sdk_client,
    normalize_file_input,
)


class TextRecognitionTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Invoke the PaddleOCR API to recognize the text in the image."""
        if "aistudio_access_token" not in self.runtime.credentials:
            raise RuntimeError(
                "The AI Studio access token is not configured or invalid. Please provide it in the plugin settings."
            )
        access_token = self.runtime.credentials["aistudio_access_token"]

        # Get base_url (optional, uses SDK default if not provided)
        base_url = self.runtime.credentials.get("base_url")

        # Normalize file input - returns (input_value, is_temp_file, file_type_code)
        file_input, is_temp_file, file_type_code = normalize_file_input(
            tool_parameters.get("file"), tool_parameters.get("fileType")
        )

        try:
            # Build OCR options from parameters
            options = build_ocr_options(tool_parameters)

            # Get API client config
            client_config = get_sdk_client(access_token, base_url)

            # Call API
            if file_input.startswith(("http://", "https://")):
                result = call_paddleocr_api(
                    model="PP-OCRv5",
                    file_url=file_input,
                    file_path=None,
                    options=options,
                    client_config=client_config,
                    is_document_parsing=False,
                )
            else:
                result = call_paddleocr_api(
                    model="PP-OCRv5",
                    file_url=None,
                    file_path=file_input,
                    options=options,
                    client_config=client_config,
                    is_document_parsing=False,
                )

            # Extract text for output
            all_text = []
            for page in result["pages"]:
                pruned = page["pruned_result"]
                if pruned and "rec_texts" in pruned:
                    text_list = pruned["rec_texts"]
                    if text_list is not None:
                        all_text.append("\n".join(text_list))

            yield self.create_text_message("\n\n".join(all_text))

            # Return raw result as JSON
            yield self.create_json_message({
                "job_id": result["job_id"],
                "pages": [
                    {
                        "pruned_result": page["pruned_result"],
                        "ocr_image_url": page["ocr_image_url"],
                    }
                    for page in result["pages"]
                ]
            })

        finally:
            # Clean up temporary file if created
            cleanup_temp_file(file_input, is_temp_file)