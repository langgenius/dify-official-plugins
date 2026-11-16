from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .seventeentrack_client import SeventeenTrackClient


class GetQuotaTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = SeventeenTrackClient(
            self.runtime.credentials["seventeen_track_api_key"]
        )
        yield self.create_json_message(client.get_quota())
