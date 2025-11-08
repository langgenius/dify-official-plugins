from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_task_api_v2_utils import FeishuRequestV2


class AddMembersTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequestV2(app_id, app_secret)
        task_guid = tool_parameters.get("task_guid")
        userID = tool_parameters.get("userID") 
        member_role = tool_parameters.get("member_role", "follower")
        res = client.add_members(task_guid, userID, member_role)
        yield self.create_json_message(res)
