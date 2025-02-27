from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class UpdateTaskTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        task_guid = tool_parameters.get("task_guid")
        summary = tool_parameters.get("summary")
        start_time = tool_parameters.get("start_time")
        end_time = tool_parameters.get("end_time")
        completed_time = tool_parameters.get("completed_time")
        description = tool_parameters.get("description")
        res = client.update_task(task_guid, summary, start_time, end_time, completed_time, description)
        yield self.create_json_message(res)
