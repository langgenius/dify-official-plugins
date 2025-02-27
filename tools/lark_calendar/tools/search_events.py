from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from lark_api_utils import LarkRequest


class SearchEventsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        query = tool_parameters.get("query")
        start_time = tool_parameters.get("start_time")
        end_time = tool_parameters.get("end_time")
        page_token = tool_parameters.get("page_token")
        user_id_type = tool_parameters.get("user_id_type", "open_id")
        page_size = tool_parameters.get("page_size", 20)
        res = client.search_events(
            query, start_time, end_time, page_token, user_id_type, page_size
        )
        yield self.create_json_message(res)
