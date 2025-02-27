from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class CreateSpreadsheetTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        title = tool_parameters.get("title")
        folder_token = tool_parameters.get("folder_token")
        res = client.create_spreadsheet(title, folder_token)
        yield self.create_json_message(res)
