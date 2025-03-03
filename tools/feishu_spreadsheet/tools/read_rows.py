from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_api_utils import FeishuRequest


class ReadRowsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        spreadsheet_token = tool_parameters.get("spreadsheet_token")
        sheet_id = tool_parameters.get("sheet_id")
        sheet_name = tool_parameters.get("sheet_name")
        start_row = tool_parameters.get("start_row")
        num_rows = tool_parameters.get("num_rows")
        user_id_type = tool_parameters.get("user_id_type", "open_id")
        res = client.read_rows(
            spreadsheet_token, sheet_id, sheet_name, start_row, num_rows, user_id_type
        )
        yield self.create_json_message(res)
