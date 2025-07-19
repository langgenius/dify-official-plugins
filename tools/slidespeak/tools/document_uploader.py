import traceback
from typing import Any, Generator
from dataclasses import dataclass

import httpx
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from dify_plugin.file.file import File

from .slidespeak_client import SlideSpeakClient


class DocumentUploaderTool(Tool):
    """Tool for uploading documents to the SlideSpeak API"""

    @dataclass
    class UploadRequest:
        file: Any  # Expected to be a dify_plugin File object or a URL string

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Synchronous invoke method"""
        # Extract required parameter
        file_param = tool_parameters.get("file")
        if not file_param:
            yield self.create_text_message("Error: file is required")
            return

        # Download file content if the parameter is a File object or a URL
        try:
            if isinstance(file_param, File):
                filename = file_param.filename or "uploaded_document"
                download_url = file_param.url
            elif isinstance(file_param, str):
                filename = file_param.split("/")[-1] or "uploaded_document"
                download_url = file_param
            else:
                yield self.create_text_message(
                    "Error: file must be a valid uploaded file or URL string"
                )
                return

            # Fetch the file bytes
            download_response = httpx.get(download_url)
            download_response.raise_for_status()
            file_bytes = download_response.content
        except Exception as e:
            traceback.print_exc()
            yield self.create_text_message(f"Error downloading file: {str(e)}")
            return

        try:
            # Create SlideSpeak client
            client = SlideSpeakClient.from_runtime_credentials(self.runtime)

            # Upload document using the centralized client method
            document_uuid = client.upload_document_and_get_uuid(file_bytes, filename)

            yield self.create_text_message(
                f"Document uploaded successfully. Document UUID: {document_uuid}"
            )

            # Create JSON message with the response format
            response_data = {
                "task_id": document_uuid,
                "task_status": "SUCCESS",
                "task_result": document_uuid,
                "task_info": document_uuid,
            }
            yield self.create_json_message(response_data)

            # Return as variable so that downstream tools can reference it
            yield self.create_variable_message("document_uuid", document_uuid)

        except Exception as e:
            traceback.print_exc()
            # Create JSON message for error case
            error_response = {
                "task_id": None,
                "task_status": "FAILURE",
                "task_result": None,
                "task_info": str(e),
            }
            yield self.create_json_message(error_response)
            yield self.create_text_message(f"An error occurred during upload: {str(e)}")
