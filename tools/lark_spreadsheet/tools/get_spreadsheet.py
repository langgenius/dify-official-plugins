from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class GetSpreadsheetTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        spreadsheet_token = tool_parameters.get("spreadsheet_token")
        user_id_type = tool_parameters.get("user_id_type", "open_id")
        res = client.get_spreadsheet(spreadsheet_token, user_id_type)
        yield self.create_json_message(res)
