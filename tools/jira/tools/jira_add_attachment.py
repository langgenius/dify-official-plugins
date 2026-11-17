from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from tools.jira_client import JiraAuthError, attachment_dict, jira_request, require, resolve_context, segment
from tools.outputs import with_outputs


class JiraAddAttachmentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Attach a file (or text written by the agent) to an issue."""
        file: File | None = tool_parameters.get("file")
        file_name = str(tool_parameters.get("file_name") or "").strip()
        text = tool_parameters.get("file_content")
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (key,) = require(tool_parameters, "issue_key")
            if file:
                content, name, mime = file.blob, file_name or file.filename, file.mime_type
            elif text:
                if not file_name:
                    raise JiraAuthError("A file name (such as notes.txt) is required when attaching text.")
                content, name, mime = str(text).encode("utf-8"), file_name, "text/plain"
            else:
                raise JiraAuthError("A file or some text content is required.")
            if not content:
                raise JiraAuthError("The file is empty.")
            attachments = jira_request(
                ctx, "POST", ctx.api(f"issue/{segment(key)}/attachments"),
                files={"file": (name or "attachment", content, mime or "application/octet-stream")},
                # Jira requires this header on multipart uploads (XSRF protection).
                headers={"X-Atlassian-Token": "no-check"},
                timeout=300,
            ).json()
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        result = [attachment_dict(a) for a in attachments or []]
        first = result[0] if result else {"id": "", "filename": name, "size": len(content)}
        self._out.update(attachment_id=first["id"], filename=first["filename"], size=first["size"], success=True)
        yield self.create_json_message({"issue_key": key, "attachments": result})
        yield self.create_text_message(f"Attached {first['filename']} to {key}.")
