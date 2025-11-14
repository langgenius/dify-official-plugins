from typing import Any, Generator
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_task_api_v2_utils import FeishuRequestV2, normalize_list

class GetUserIDTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequestV2(app_id, app_secret)
        email_or_phone = tool_parameters.get("email_or_phone")

        normalized_contacts = normalize_list(email_or_phone)
        res = client.get_userID_from_email_phone(normalized_contacts)
        yield self.create_json_message(res)