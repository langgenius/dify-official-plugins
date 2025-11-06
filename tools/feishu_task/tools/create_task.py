from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_task_api_v2_utils import FeishuRequestV2


class CreateTaskTool(Tool):
    '''def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequest(app_id, app_secret)
        summary = tool_parameters.get("summary")
        start_time = tool_parameters.get("start_time")
        end_time = tool_parameters.get("end_time")
        completed_time = tool_parameters.get("completed_time")
        description = tool_parameters.get("description")
        res = client.create_task(
            summary, start_time, end_time, completed_time, description
        )
        yield self.create_json_message(res)'''

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        tz = self.runtime.credentials.get("time_zone", "Asia/Shanghai")
        client = FeishuRequestV2(app_id, app_secret, tz)
        summary = tool_parameters.get("summary")
        description = tool_parameters.get("description")
        start_time = tool_parameters.get("start_time")
        start_time_is_all_day = tool_parameters.get("start_time_is_all_day")
        due_date = tool_parameters.get("due_date")
        end_time_is_all_day = tool_parameters.get("end_time_is_all_day")
        completed_at = tool_parameters.get("completed_at")
        relative_fire_minute = tool_parameters.get("relative_fire_minute")
        assignees_members = tool_parameters.get("assignees_members")
        followers_members = tool_parameters.get("followers_members")
        res = client.create_task(
            summary, description, start_time, start_time_is_all_day, due_date, end_time_is_all_day, completed_at, relative_fire_minute, assignees_members, followers_members
        )
        yield self.create_json_message(res)
