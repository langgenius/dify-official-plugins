from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class ReadColsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        spreadsheet_token = tool_parameters.get("spreadsheet_token")
        sheet_id = tool_parameters.get("sheet_id")
        sheet_name = tool_parameters.get("sheet_name")
        start_col = tool_parameters.get("start_col")
        num_cols = tool_parameters.get("num_cols")
        user_id_type = tool_parameters.get("user_id_type", "open_id")
        res = client.read_cols(spreadsheet_token, sheet_id, sheet_name, start_col, num_cols, user_id_type)
        yield self.create_json_message(res)
