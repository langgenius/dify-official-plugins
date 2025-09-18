import asyncio
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from msgraph.generated.models.drive_item import DriveItem

from .utils import OneDriveClient


class GetFileByIdTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        file_id = tool_parameters.get("file_id")
        download = tool_parameters.get("download", False)

        if not file_id:
            yield self.create_text_message("File ID is required.")
            yield self.create_json_message({"error": "File ID is required."})
            return

        client: OneDriveClient = OneDriveClient(self.runtime.credentials)

        try:
            file: DriveItem = asyncio.run(client.get_file_by_id(file_id))

            if not file:
                yield self.create_text_message("File not found.")
                yield self.create_json_message({"error": "File not found."})
                return

            file_info = {
                "id": file.id,
                "name": file.name,
                "size": file.size,  # In bytes
                "download_url": (
                    file.additional_data.get("@microsoft.graph.downloadUrl")
                    if file.additional_data
                    else None
                ),
                "last_modified_date_time": (
                    file.last_modified_date_time.isoformat()
                    if file.last_modified_date_time
                    else None
                ),
                "path": (file.parent_reference.path if file.parent_reference else None),
                "drive_id": (
                    file.parent_reference.drive_id if file.parent_reference else None
                ),
            }

            yield self.create_json_message(file_info)
            if (
                download
                and file_info.get("download_url")
                and file_info.get("size", 0) < 15 * 1024 * 1024
            ):
                response = requests.get(file_info["download_url"], timeout=30)
                if response.status_code == 200:
                    yield self.create_blob_message(
                        blob=response.content,
                        meta={
                            "file_name": file_info["name"],
                        },
                    )

        except Exception as e:
            yield self.create_json_message({"error": str(e)})
            yield self.create_text_message(f"Error retrieving file: {e}")
