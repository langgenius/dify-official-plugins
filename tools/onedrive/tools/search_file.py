import asyncio
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import OneDriveClient


class SearchFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        client = OneDriveClient(self.runtime.credentials)
        query = tool_parameters.get("query")
        limit = tool_parameters.get("limit", 10)

        if not query:
            yield self.create_text_message("Query parameter is required.")
            yield self.create_json_message({"error": "Query parameter is required."})
            return

        files = asyncio.run(client.search_file(query)).value
        if len(files) > limit:
            files = files[:limit]

        try:
            results = [
                {
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
                    "path": (
                        file.parent_reference.path if file.parent_reference else None
                    ),
                    "drive_id": (
                        file.parent_reference.drive_id
                        if file.parent_reference
                        else None
                    ),
                }
                for file in files
            ]

            yield self.create_json_message({"results": results})
        except Exception as e:
            yield self.create_text_message(f"Error searching files: {e}")
            yield self.create_json_message({"error": str(e)})
