from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.jira_client import JiraAuthError, attachment_dict, jira_request, require, resolve_context, segment
from tools.outputs import with_outputs

# Larger files are described but not downloaded into the conversation.
MAX_DOWNLOAD = 50 * 1024 * 1024


class JiraGetAttachmentTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """An attachment's details and, unless download is off, the file itself."""
        download = tool_parameters.get("download") is not False
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            (attachment_id,) = require(tool_parameters, "attachment_id")
            meta = jira_request(ctx, "GET", ctx.api(f"attachment/{segment(attachment_id)}")).json()
            info = attachment_dict(meta)
            content = None
            if download and info["size"] <= MAX_DOWNLOAD:
                # The content URL in the metadata is on the site host, which does not accept OAuth tokens;
                # this route works for every credential mode. Jira answers with a redirect to its media
                # store, and requests drops the Authorization header when the host changes.
                url = ctx.api(f"attachment/content/{segment(attachment_id)}")
                # Older Server / Data Center versions only have the download link in the metadata;
                # follow it only when it is on the configured Jira host, so the token goes nowhere else.
                if not ctx.cloud and str(meta.get("content", "")).startswith(ctx.base_url + "/"):
                    url = meta["content"]
                content = jira_request(ctx, "GET", url, headers={"Accept": "*/*"}, timeout=300).content
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(attachment=info, filename=info["filename"], success=True)
        yield self.create_json_message(info)
        if content is not None:
            yield self.create_blob_message(
                content, meta={"mime_type": info["mime_type"] or "application/octet-stream", "filename": info["filename"]}
            )
            yield self.create_text_message(f"Downloaded {info['filename']} ({info['size']} bytes).")
        elif download:
            yield self.create_text_message(
                f"{info['filename']} is {info['size']} bytes, over the {MAX_DOWNLOAD // (1024 * 1024)} MB download limit; "
                "only its details were returned."
            )
        else:
            yield self.create_text_message(f"{info['filename']}: {info['size']} bytes, {info['mime_type']}.")
