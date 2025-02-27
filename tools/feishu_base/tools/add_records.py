from collections.abc import Generator
from typing import Any
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from tools.feishu_api_utils import FeishuRequest


class AddRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        app_token = tool_parameters.get("app_token")
        table_id = tool_parameters.get("table_id")
        table_name = tool_parameters.get("table_name")
        records = tool_parameters.get("records")
        user_id_type = tool_parameters.get("user_id_type", "open_id")
        res = client.add_records(app_token, table_id, table_name, records, user_id_type)
        yield self.create_json_message(res)
