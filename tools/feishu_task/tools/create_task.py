from typing import Any, Generator
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_task_api_v2_utils import FeishuRequestV2


class CreateTaskTool(Tool):
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
        assignees_members = tool_parameters.get("assignees_members") or []
        followers_members = tool_parameters.get("followers_members") or []

        def normalize_members(members):
            """兼容字符串 / JSON 字符串 / list 输入"""
            if isinstance(members, list):
                return [str(x).strip() for x in members if x]
            if isinstance(members, str):
                members = members.strip()
                if not members:
                    return []
                try:
                    parsed = json.loads(members)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if x]
                    elif isinstance(parsed, str):
                        return [parsed.strip()]
                except json.JSONDecodeError:
                    members = members.strip("{} ")
                    return [m.strip().strip('"') for m in members.split(",") if m.strip()]
            return []

        assignees_members = normalize_members(assignees_members)
        followers_members = normalize_members(followers_members)

        res = client.create_task(
            summary,
            description,
            start_time,
            start_time_is_all_day,
            due_date,
            end_time_is_all_day,
            completed_at,
            relative_fire_minute,
            assignees_members,
            followers_members,
            tz,
        )

        yield self.create_json_message(res)
