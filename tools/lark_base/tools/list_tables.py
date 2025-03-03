from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from lark_api_utils import LarkRequest


class ListTablesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        app_token = tool_parameters.get("app_token")
        page_token = tool_parameters.get("page_token")
        page_size = tool_parameters.get("page_size", 20)
        res = client.list_tables(app_token, page_token, page_size)
        yield self.create_json_message(res)
