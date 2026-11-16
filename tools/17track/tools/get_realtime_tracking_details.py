from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .seventeentrack_client import SeventeenTrackClient


class GetRealtimeTrackingDetailsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = SeventeenTrackClient(
            self.runtime.credentials["seventeen_track_api_key"]
        )
        number = tool_parameters.get("number")
        if not number:
            raise ValueError("number is required")
        cache_level = tool_parameters.get("cache_level") or 0
        result = client.get_realtime_tracking_details(
            {"number": number, "cacheLevel": int(cache_level)}
        )
        yield self.create_json_message(result)
