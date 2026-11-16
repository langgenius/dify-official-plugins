from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .seventeentrack_client import SeventeenTrackClient, SeventeenTrackError


class GetTrackingDetailsTool(Tool):
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
        result = client.get_tracking_details(
            [{"number": number} for number in numbers]
        )
        yield self.create_json_message(result)
