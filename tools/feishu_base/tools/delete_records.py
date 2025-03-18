from collections.abc import Generator
from typing import Any
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.feishu_api_utils import FeishuRequest


class DeleteRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        app_token = tool_parameters.get("app_token")
        table_id = tool_parameters.get("table_id")
        table_name = tool_parameters.get("table_name")
        record_ids = tool_parameters.get("record_ids")
        res = client.delete_records(app_token, table_id, table_name, record_ids)
        yield self.create_json_message(res)
