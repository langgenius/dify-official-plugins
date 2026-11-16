from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .seventeentrack_client import SeventeenTrackClient, SeventeenTrackError


class UpdateTrackingInfoTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = SeventeenTrackClient(
            self.runtime.credentials["seventeen_track_api_key"]
        )
        numbers = client.parse_numbers(tool_parameters.get("numbers") or "")
        if not numbers or len(numbers) > 40:
            raise SeventeenTrackError(
                None, "Provide between 1 and 40 valid tracking numbers"
            )
        items = {}
        if tool_parameters.get("tag"):
            items["tag"] = tool_parameters["tag"]
        if tool_parameters.get("lang"):
            items["lang"] = tool_parameters["lang"]
        if tool_parameters.get("remark"):
            items["remark"] = tool_parameters["remark"]
        if not items:
            raise SeventeenTrackError(
                None, "Provide at least one field to update (tag, lang or remark)"
            )
        result = client.update_tracking_info(
            [{"number": number, "items": items} for number in numbers]
        )
        yield self.create_json_message(result)
