import asyncio
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from kiota_abstractions.api_error import APIError

from .utils import OneDriveClient


class UploadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file: File = tool_parameters.get("file")
        custom_file_name = tool_parameters.get("file_name")

        if not file:
            yield self.create_text_message("File is required.")
            yield self.create_json_message({"error": "File is required."})
            return

        file_content = file.blob
        original_file_name = file.filename

        file_name = custom_file_name if custom_file_name else original_file_name

        if not file_content:
            yield self.create_text_message("File content is empty.")
            yield self.create_json_message({"error": "File content is empty."})
            return

        client = OneDriveClient(self.runtime.credentials)

        try:
            uploaded_file = asyncio.run(client.upload_file(file_name, file_content))

            if uploaded_file:
                file_info = {
                    "id": uploaded_file.id,
                    "name": uploaded_file.name,
                    "size": uploaded_file.size,
                    "download_url": (
                        uploaded_file.additional_data.get(
                            "@microsoft.graph.downloadUrl"
                        )
                        if uploaded_file.additional_data
                        else None
                    ),
                    "created_date_time": (
                        uploaded_file.created_date_time.isoformat()
                        if uploaded_file.created_date_time
                        else None
                    ),
                    "last_modified_date_time": (
                        uploaded_file.last_modified_date_time.isoformat()
                        if uploaded_file.last_modified_date_time
                        else None
                    ),
                    "path": (
                        uploaded_file.parent_reference.path
                        if uploaded_file.parent_reference
                        else None
                    ),
                    "drive_id": (
                        uploaded_file.parent_reference.drive_id
                        if uploaded_file.parent_reference
                        else None
                    ),
                    "web_url": uploaded_file.web_url,
                }

                yield self.create_text_message(
                    f"File uploaded successfully: {file_info}"
                )
                yield self.create_json_message(file_info)
            else:
                yield self.create_text_message(f"File upload failed: {uploaded_file}")
                yield self.create_json_message({"error": "File upload failed."})

        except APIError as e:
            error_message = f"OneDrive API error: {str(e)}"
            yield self.create_text_message(error_message)
            yield self.create_json_message({"error": error_message})
        except Exception as e:
            error_message = f"Error uploading file: {str(e)}"
            yield self.create_text_message(error_message)
            yield self.create_json_message({"error": error_message})
