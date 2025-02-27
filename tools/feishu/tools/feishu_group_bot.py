from collections.abc import Generator
from typing import Any
import uuid
import httpx
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


def is_valid_uuid(uuid_str: str) -> bool:
    try:
        uuid.UUID(uuid_str)
        return True
    except ValueError:
        return False


class FeishuGroupBotTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        API document: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
        """
        url = "https://open.feishu.cn/open-apis/bot/v2/hook"
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
            return
        hook_key = tool_parameters.get("hook_key", "")
        if not is_valid_uuid(hook_key):
            yield self.create_text_message(
                f"Invalid parameter hook_key ${hook_key}, not a valid UUID"
            )
            return
        msg_type = "text"
        api_url = f"{url}/{hook_key}"
        headers = {"Content-Type": "application/json"}
        params = {}
        payload = {"msg_type": msg_type, "content": {"text": content}}
        try:
            res = httpx.post(api_url, headers=headers, params=params, json=payload)
            if res.is_success:
                yield self.create_text_message("Text message sent successfully")
            else:
                yield self.create_text_message(
                    f"Failed to send the text message, status code: {res.status_code}, response: {res.text}"
                )
        except Exception as e:
            yield self.create_text_message(
                "Failed to send message to group chat bot. {}".format(e)
            )
