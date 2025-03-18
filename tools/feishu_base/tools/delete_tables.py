from collections.abc import Generator
from typing import Any
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.feishu_api_utils import FeishuRequest


class DeleteTablesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        app_token = tool_parameters.get("app_token")
        table_ids = tool_parameters.get("table_ids")
        table_names = tool_parameters.get("table_names")
        res = client.delete_tables(app_token, table_ids, table_names)
        yield self.create_json_message(res)
