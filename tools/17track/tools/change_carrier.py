from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .seventeentrack_client import SeventeenTrackClient, SeventeenTrackError


class ChangeCarrierTool(Tool):
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
        carrier_new = tool_parameters.get("carrier_new")
        if not carrier_new:
            raise SeventeenTrackError(None, "carrier_new is required")
        result = client.change_carrier(
            [
                {"number": number, "carrier_new": int(carrier_new)}
                for number in numbers
            ]
        )
        yield self.create_json_message(result)
