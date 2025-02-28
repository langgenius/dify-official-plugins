from typing import Any
from collections.abc import Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.feishu_api_utils import FeishuRequest


class GetChatMessagesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        container_id = tool_parameters.get("container_id")
        page_token = tool_parameters.get("page_token")
        sort_type = tool_parameters.get("sort_type", "ByCreateTimeAsc")
        page_size = tool_parameters.get("page_size", 20)
        res = client.get_thread_messages(container_id, page_token, sort_type, page_size)
        yield self.create_json_message(res)
