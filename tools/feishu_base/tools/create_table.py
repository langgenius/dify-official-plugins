from typing import Any
from collections.abc import Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.feishu_api_utils import FeishuRequest


class CreateTableTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        app_token = tool_parameters.get("app_token")
        table_name = tool_parameters.get("table_name")
        default_view_name = tool_parameters.get("default_view_name")
        fields = tool_parameters.get("fields")
        res = client.create_table(app_token, table_name, default_view_name, fields)
        yield self.create_json_message(res)
