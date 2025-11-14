from typing import Any, Generator
import logging

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
        member_ids = tool_parameters.get("member_ids")
        member_phone_or_email = tool_parameters.get("member_phone_or_email")
        member_role = tool_parameters.get("member_role", "follower")
        member_type = tool_parameters.get("member_type", "user")
        client_token = tool_parameters.get("client_token")

        def normalize_list(v):
            if isinstance(v, list):
                return [str(x).strip() for x in v if x]
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    return []
                try:
                    import json
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if x]
                except Exception:
                    pass
                s = s.replace("{", "").replace("}", "").replace("[", "").replace("]", "")
                s = s.replace('"', "").replace("'", "")
                return [x.strip() for x in s.split(",") if x.strip()]
            return []

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
                contacts = normalize_list(member_phone_or_email)
                if contacts:
                    res_ids = client.get_userID_from_email_phone(contacts)
                    data = res_ids.get("data", {}) if isinstance(res_ids, dict) else {}
                    extracted = []
                    for k in ["users", "user_infos", "items", "data"]:
                        v = data.get(k)
                        if isinstance(v, list):
                            for it in v:
                                if isinstance(it, dict):
                                    uid = it.get("open_id") or it.get("user_id") or it.get("id")
                                    if uid:
                                        extracted.append(str(uid))
                    user_ids = extracted

            if not user_ids:
                raise ValueError("member_ids or member_phone_or_email must provide at least one member")

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
