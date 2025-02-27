from typing import Any
from collections.abc import Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.feishu_api_utils import FeishuRequest


class SendWebhookMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        webhook = tool_parameters.get("webhook")
        msg_type = tool_parameters.get("msg_type")
        content = tool_parameters.get("content")
        res = client.send_webhook_message(webhook, msg_type, content)
        yield self.create_json_message(res)
