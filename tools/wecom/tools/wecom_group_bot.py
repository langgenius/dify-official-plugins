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
    def _upload_file(self, hook_key: str, file_content: bytes, filename: str) -> dict:
        """
        Upload file to get media_id
        """
        upload_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media"
        params = {"key": hook_key, "type": "file"}
        files = {
            "media": (filename, file_content, "application/octet-stream")
        }
        res = httpx.post(upload_url, params=params, files=files)
        if res.is_success:
            return res.json()
        else:
            raise Exception(f"Failed to upload file, status code: {res.status_code}, response: {res.text}")

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        hook_key = tool_parameters.get("hook_key", "")
        if not is_valid_uuid(hook_key):
            yield self.create_text_message(f"Invalid parameter hook_key ${hook_key}, not a valid UUID")
            return

        message_type = tool_parameters.get("message_type", "text")

        if message_type == "file":
            # Handle file type message
            file = tool_parameters.get("file")
            if not file:
                yield self.create_text_message("Invalid parameter file: file is required for file message type")
                return
            try:
                # Upload file to get media_id
                upload_result = self._upload_file(hook_key, file.blob, file.filename or "file")
                if upload_result.get("errcode") != 0:
                    yield self.create_text_message(
                        f"Failed to upload file: {upload_result.get('errmsg', 'Unknown error')}"
                    )
                    return
                media_id = upload_result.get("media_id")
                if not media_id:
                    yield self.create_text_message("Failed to get media_id from upload response")
                    return
                payload = {"msgtype": "file", "file": {"media_id": media_id}}
            except Exception as e:
                yield self.create_text_message(f"Failed to upload file: {e}")
                return
        else:
            # Handle text/markdown message types
            content = tool_parameters.get("content", "")
            if not content:
                yield self.create_text_message("Invalid parameter content")
                return
            if message_type == "markdown":
                payload = {"msgtype": "markdown", "markdown": {"content": content}}
            elif message_type == "markdown_v2":
                payload = {"msgtype": "markdown_v2", "markdown_v2": {"content": content}}
            else:
                payload = {"msgtype": "text", "text": {"content": content}}

        api_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
        headers = {"Content-Type": "application/json"}
        params = {"key": hook_key}
        try:
            res = httpx.post(api_url, headers=headers, params=params, json=payload)
            if res.is_success:
                yield self.create_text_message("Message sent successfully")
            else:
                yield self.create_text_message(
                    f"Failed to send the message, status code: {res.status_code}, response: {res.text}"
                )
        except Exception as e:
            yield self.create_text_message("Failed to send message to group chat bot. {}".format(e))
