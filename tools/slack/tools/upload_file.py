from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class UploadFileTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        filename = (tool_parameters.get("filename") or "").strip()
        file_obj = tool_parameters.get("file")
        content = tool_parameters.get("content")

        data_bytes: bytes | None = None
        if file_obj is not None:
            try:
                data_bytes = file_obj.blob
            except AttributeError:
                yield self.create_text_message("Could not read the provided file.")
                return
            if not filename:
                filename = getattr(file_obj, "filename", None) or "upload"
        elif content is not None and content != "":
            data_bytes = str(content).encode("utf-8")
            if not filename:
                filename = "upload.txt"
        else:
            yield self.create_text_message("Provide a 'file' or 'content' to upload.")
            return

        length = len(data_bytes)

        # Step 1: reserve an upload URL.
        try:
            r1 = client.call(
                "files.getUploadURLExternal",
                "GET",
                params={"filename": filename, "length": length},
            )
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed (get upload URL): {e}")
            return
        ok, d1, error = slack_result(r1)
        if not ok:
            yield self.create_json_message(d1)
            yield self.create_text_message(f"Slack error: {error}")
            return
        upload_url = d1.get("upload_url")
        file_id = d1.get("file_id")

        # Step 2: POST the bytes to the reserved URL.
        try:
            up = requests.post(
                upload_url, files={"file": (filename, data_bytes)}, timeout=120
            )
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed (upload bytes): {e}")
            return
        if up.status_code >= 400:
            yield self.create_text_message(
                f"Byte upload failed (HTTP {up.status_code})."
            )
            return

        # Step 3: complete the upload, optionally sharing to a channel.
        file_entry: dict[str, Any] = {"id": file_id}
        if tool_parameters.get("title"):
            file_entry["title"] = tool_parameters.get("title")
        body: dict[str, Any] = {"files": [file_entry]}
        if tool_parameters.get("channel"):
            body["channel_id"] = tool_parameters.get("channel")
        if tool_parameters.get("initial_comment"):
            body["initial_comment"] = tool_parameters.get("initial_comment")
        if tool_parameters.get("thread_ts"):
            body["thread_ts"] = tool_parameters.get("thread_ts")

        try:
            r3 = client.call(
                "files.completeUploadExternal", "POST", json_body=body
            )
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed (complete upload): {e}")
            return
        ok, d3, error = slack_result(r3)
        yield self.create_json_message(d3)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        yield self.create_text_message(f"File '{filename}' uploaded (id {file_id}).")
