from typing import Any, Generator
import httpx
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
import uuid

def is_valid_uuid(uuid_str: str) -> bool:
    try:
        uuid.UUID(uuid_str)
        return True
    except Exception:
        return False


class WecomGroupBotTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
        hook_key = tool_parameters.get("hook_key", "")
        if not is_valid_uuid(hook_key):
            yield self.create_text_message(f"Invalid parameter hook_key ${hook_key}, not a valid UUID")
        message_type = tool_parameters.get("message_type", "text")
        if message_type == "markdown":
            payload = {"msgtype": "markdown", "markdown": {"content": content}}
        elif  message_type == "markdown_v2":
            payload = {"msgtype": "markdown_v2", "markdown_v2": {"content": content}}
        else:
            payload = {"msgtype": "text", "text": {"content": content}}
        api_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
        headers = {"Content-Type": "application/json"}
        params = {"key": hook_key}
        try:
            res = httpx.post(api_url, headers=headers, params=params, json=payload)
            if res.is_success:
                yield self.create_text_message("Text message sent successfully")
            else:
                yield self.create_text_message(
                    f"Failed to send the text message, status code: {res.status_code}, response: {res.text}"
                )
        except Exception as e:
            yield self.create_text_message("Failed to send message to group chat bot. {}".format(e))
