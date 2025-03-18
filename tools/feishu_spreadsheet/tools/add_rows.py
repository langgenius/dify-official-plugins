from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_api_utils import FeishuRequest


class AddRowsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        spreadsheet_token = tool_parameters.get("spreadsheet_token")
        sheet_id = tool_parameters.get("sheet_id")
        sheet_name = tool_parameters.get("sheet_name")
        length = tool_parameters.get("length")
        values = tool_parameters.get("values")
        res = client.add_rows(spreadsheet_token, sheet_id, sheet_name, length, values)
        yield self.create_json_message(res)
