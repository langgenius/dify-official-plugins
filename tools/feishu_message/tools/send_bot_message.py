from typing import Any
from collections.abc import Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.feishu_api_utils import FeishuRequest


class SendBotMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        receive_id_type = tool_parameters.get("receive_id_type")
        receive_id = tool_parameters.get("receive_id")
        msg_type = tool_parameters.get("msg_type")
        content = tool_parameters.get("content")
        res = client.send_bot_message(receive_id_type, receive_id, msg_type, content)
        yield self.create_json_message(res)
