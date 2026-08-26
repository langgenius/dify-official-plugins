import logging
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.utils import (
    DEFAULT_VL_MODEL,
    DOCX_MIME_TYPE,
    build_optional_payload,
    call_paddleocr_api,
    cleanup_temp_file,
    get_api_client_config,
    iter_docx_exports,
    normalize_file_input,
    render_document_markdown,
    validate_layout_options,
    validate_vl_options,
)

logger = logging.getLogger(__name__)


def build_paddleocr_vl_options(params: dict[str, Any]) -> dict[str, Any]:
    """Build the camelCase optional payload expected by the HTTP API."""
    options = build_optional_payload(params)
    validate_layout_options(options)
    validate_vl_options(options)
    return options


class DocumentParsingVlTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Invoke the PaddleOCR API to parse the document images using a VLM."""
        access_token = self.runtime.credentials.get("aistudio_access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise RuntimeError(
                "The AI Studio access token is not configured or invalid. "
                "Please provide it in the plugin settings."
            )

        # Get base_url (optional, uses default if not provided)
        base_url = self.runtime.credentials.get("base_url")

        # Normalize file input - returns (input_value, is_temp_file, file_type_code)
        file_input, is_temp_file, _file_type_code = normalize_file_input(
            tool_parameters.get("file"), tool_parameters.get("fileType")
        )

        try:
            # Build options from parameters
            options = build_paddleocr_vl_options(tool_parameters)

            # Get API client config
            client_config = get_api_client_config(access_token, base_url=base_url)

            # Get model selection
            model = tool_parameters.get("model") or DEFAULT_VL_MODEL
            page_ranges = tool_parameters.get("pageRanges")

            # Call API
            if file_input.startswith(("http://", "https://")):
                result = call_paddleocr_api(
                    model=model,
                    file_url=file_input,
                    file_path=None,
                    options=options,
                    client_config=client_config,
                    is_document_parsing=True,
                    page_ranges=page_ranges,
                )
            else:
                result = call_paddleocr_api(
                    model=model,
                    file_url=None,
                    file_path=file_input,
                    options=options,
                    client_config=client_config,
                    is_document_parsing=True,
                    page_ranges=page_ranges,
                )

            markdown_text = render_document_markdown(
                result,
                self,
                image_filename_prefix="paddleocr_vl_image",
                warning_logger=logger,
            )
            yield self.create_text_message(markdown_text)

            for filename, document_bytes in iter_docx_exports(
                result,
                filename_prefix="paddleocr-vl-document",
                warning_logger=logger,
            ):
                yield self.create_blob_message(
                    blob=document_bytes,
                    meta={"filename": filename, "mime_type": DOCX_MIME_TYPE},
                )

            # Return raw result as JSON
            yield self.create_json_message(
                {
                    "job_id": result["job_id"],
                    "pages": [
                        {
                            "markdown_text": page["markdown_text"],
                            "markdown_images": page["markdown_images"],
                            "output_images": page["output_images"],
                        }
                        for page in result["pages"]
                    ],
                }
            )

        finally:
            # Clean up temporary file if created
            cleanup_temp_file(file_input, is_temp_file)
