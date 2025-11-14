from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_task_api_v2_utils import FeishuRequestV2


class UpdateTaskTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        tz = self.runtime.credentials.get("time_zone", "Asia/Shanghai")
        client = FeishuRequestV2(app_id, app_secret, tz)
        task_guid = tool_parameters.get("task_guid")
        summary = tool_parameters.get("summary")
        description = tool_parameters.get("description") or None
        start_time = tool_parameters.get("start_time") or None
        end_time = tool_parameters.get("end_time") or None
        completed_time = tool_parameters.get("completed_time") or None
        res = client.update_task(
            task_guid,
            summary,
            description,
            start_time,
            end_time,
            completed_time,
            tz,
        )
        yield self.create_json_message(res)
