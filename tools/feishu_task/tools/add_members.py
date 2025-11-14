from typing import Any, Generator
import logging

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from feishu_task_api_v2_utils import FeishuRequestV2, normalize_list


class AddMembersTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        app_id = self.runtime.credentials.get("app_id")
        app_secret = self.runtime.credentials.get("app_secret")
        client = FeishuRequestV2(app_id, app_secret)

        task_guid = tool_parameters.get("task_guid")
        member_ids = tool_parameters.get("member_ids")
        member_role = tool_parameters.get("member_role", "follower")
        member_type = tool_parameters.get("member_type", "user")
        client_token = tool_parameters.get("client_token")

        logger = logging.getLogger(__name__)

        try:
            if not task_guid:
                raise ValueError("task_guid is required")
            if member_role not in {"assignee", "follower"}:
                raise ValueError("member_role must be 'assignee' or 'follower'")
            if member_type not in {"user", "app"}:
                raise ValueError("member_type must be 'user' or 'app'")

            user_ids = normalize_list(member_ids)

            if not user_ids:
                raise ValueError("member_ids must provide at least one member")

            logger.info("add_members start: task_guid=%s, count=%d, role=%s, type=%s", task_guid, len(user_ids), member_role, member_type)

            res = client.add_members(
                task_guid,
                user_ids,
                member_role,
                member_type,
                client_token,
            )
            logger.info("add_members success: code=%s", (res.get("code") if isinstance(res, dict) else ""))
            yield self.create_json_message(res)
        except Exception as e:
            logger.exception("add_members failed")
            err = {"error": str(e)}
            yield self.create_json_message(err)
