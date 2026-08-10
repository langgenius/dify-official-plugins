from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File

from slack_api import SlackApiError, SlackClient


class UploadFileTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        file: File = tool_parameters.get("file")
        if not file:
            yield self.create_text_message("The 'file' parameter is required.")
            return

        data = file.blob
        if not data:
            yield self.create_text_message("The provided file is empty.")
            return

        filename = file.filename or "upload"
        channel = (tool_parameters.get("channel") or "").strip() or None
        title = (tool_parameters.get("title") or "").strip() or None
        initial_comment = (tool_parameters.get("initial_comment") or "").strip() or None

        try:
            client = SlackClient(token)
            resp = client.upload_file(
                filename=filename,
                data=data,
                title=title,
                channel=channel,
                initial_comment=initial_comment,
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to upload file: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        files = resp.get("files", [])
        file_id = files[0].get("id") if files else None
        yield self.create_text_message(
            f"File '{filename}' uploaded successfully"
            + (f" (file id: {file_id})." if file_id else ".")
        )
        yield self.create_json_message(resp)
