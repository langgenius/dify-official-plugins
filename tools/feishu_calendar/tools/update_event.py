from collections.abc import Generator
from typing import Any
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.feishu_api_utils import FeishuRequest


class UpdateEventTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        event_id = tool_parameters.get("event_id")
        summary = tool_parameters.get("summary")
        description = tool_parameters.get("description")
        need_notification = tool_parameters.get("need_notification", True)
        start_time = tool_parameters.get("start_time")
        end_time = tool_parameters.get("end_time")
        auto_record = tool_parameters.get("auto_record", False)
        res = client.update_event(event_id, summary, description, need_notification, start_time, end_time, auto_record)
        yield self.create_json_message(res)
