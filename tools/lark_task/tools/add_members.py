from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.lark_api_utils import LarkRequest


class AddMembersTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = LarkRequest(app_id, app_secret)
        task_guid = tool_parameters.get("task_guid")
        member_phone_or_email = tool_parameters.get("member_phone_or_email")
        member_role = tool_parameters.get("member_role", "follower")
        res = client.add_members(task_guid, member_phone_or_email, member_role)
        yield self.create_json_message(res)
