from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .seventeentrack_client import SeventeenTrackClient


class ListTrackingsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = SeventeenTrackClient(
            self.runtime.credentials["seventeen_track_api_key"]
        )
        result = client.list_trackings(
            page_no=int(tool_parameters.get("page_no") or 0),
            package_status=tool_parameters.get("package_status") or None,
        )
        yield self.create_json_message(result)
