import logging
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import (
    DOCX_MIME_TYPE,
    call_paddleocr_api,
    cleanup_temp_file,
    get_api_client_config,
    iter_docx_exports,
    normalize_file_input,
)

_SKIP_KEYS = {"file", "fileType", "model", "pageRanges"}
logger = logging.getLogger(__name__)


def build_paddleocr_vl_options(params: dict[str, Any]) -> dict[str, Any]:
    """Build the camelCase optional payload expected by the HTTP API."""
    options_dict = {}
    for api_name, value in params.items():
        if value is None or api_name in _SKIP_KEYS:
            continue
        if api_name == "promptLabel" and value == "undefined":
            continue
        if api_name == "markdownIgnoreLabels" and isinstance(value, str):
            value = [label.strip() for label in value.split(",") if label.strip()]
        if api_name == "outputFormats":
            if value in ("", "none"):
                continue
            if isinstance(value, str):
                value = [value]
        options_dict[api_name] = value
    return options_dict


class DocumentParsingVlTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Invoke the PaddleOCR API to parse the document images using a VLM."""
        if "aistudio_access_token" not in self.runtime.credentials:
            raise RuntimeError(
                "The AI Studio access token is not configured or invalid. Please provide it in the plugin settings."
            )
        access_token = self.runtime.credentials["aistudio_access_token"]

        # Get base_url (optional, uses default if not provided)
        base_url = self.runtime.credentials.get("base_url")

        # Normalize file input - returns (input_value, is_temp_file, file_type_code)
        file_input, is_temp_file, file_type_code = normalize_file_input(
            tool_parameters.get("file"), tool_parameters.get("fileType")
        )

        try:
            # Build options from parameters
            options = build_paddleocr_vl_options(tool_parameters)

            # Get API client config
            client_config = get_api_client_config(access_token, base_url=base_url)

            # Get model selection
            model = tool_parameters.get("model") or "PaddleOCR-VL-1.6"
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

            # Process images from result
            images = []
            image_path_map = {}
            failed_images = []

            for page in result["pages"]:
                if page["markdown_images"]:
                    image_dict = page["markdown_images"]
                    if image_dict:
                        for image_path, image_url in image_dict.items():
                            if image_path in image_path_map:
                                continue
                            try:
                                import requests

                                image_bytes = requests.get(image_url, timeout=(10, 600)).content
                                file_name = f"paddleocr_vl_image_{len(images)}.jpg"
                                upload_response = self.session.file.upload(
                                    file_name, image_bytes, "image/jpeg"
                                )
                                images.append(upload_response)
                                image_path_map[image_path] = upload_response
                                if not upload_response.preview_url:
                                    failed_images.append(image_path)
                            except Exception as e:
                                logger.warning(f"Failed to process image {image_path}: {e}")
                                failed_images.append(image_path)

            # Build markdown with image replacement
            markdown_text_list = []
            for page in result["pages"]:
                markdown_text = page["markdown_text"]
                if markdown_text is not None:
                    # Replace image paths with uploaded URLs
                    for image_path, upload_response in image_path_map.items():
                        if upload_response.preview_url:
                            markdown_text = markdown_text.replace(
                                f'src="{image_path}"',
                                f'src="{upload_response.preview_url}"',
                            )
                        else:
                            markdown_text = markdown_text.replace(
                                f'src="{image_path}"', 'src="[Image unavailable]"'
                            )
                    markdown_text_list.append(markdown_text)

            yield self.create_text_message("\n\n".join(markdown_text_list))

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
