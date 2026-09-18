from collections.abc import Generator
from typing import Any
import base64
import urllib.parse
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DownloadAttachmentTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Download a single Outlook email attachment as a file, using the message
        and attachment IDs returned by Get Message. Dify hosts the returned file
        and serves it over a public HTTPS URL the user can click to download.
        """
        try:
            message_id = (tool_parameters.get("message_id") or "").strip()
            attachment_id = (tool_parameters.get("attachment_id") or "").strip()
            if not message_id:
                yield self.create_text_message("'message_id' is required.")
                return
            if not attachment_id:
                yield self.create_text_message("'attachment_id' is required.")
                return

            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Access token is required in credentials.")
                return

            enc_msg = urllib.parse.quote(message_id, safe="")
            enc_att = urllib.parse.quote(attachment_id, safe="")
            url = (
                f"https://graph.microsoft.com/v1.0/me/messages/{enc_msg}"
                f"/attachments/{enc_att}"
            )
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            try:
                response = requests.get(url, headers=headers, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if response.status_code == 401:
                yield self.create_text_message("Authentication failed. Token may be expired.")
                return
            if response.status_code == 404:
                yield self.create_text_message(
                    "Attachment not found. Check the message_id and attachment_id from Get Message."
                )
                return
            if response.status_code < 200 or response.status_code >= 300:
                yield self.create_text_message(f"API error {response.status_code}: {response.text}")
                return

            attachment = response.json()
            odata_type = attachment.get("@odata.type", "")
            name = attachment.get("name") or "attachment"
            content_type = attachment.get("contentType") or "application/octet-stream"
            content_bytes = attachment.get("contentBytes")

            # Only file attachments carry the raw bytes (contentBytes). Item/reference
            # attachments (nested emails, links) have no downloadable file.
            if odata_type != "#microsoft.graph.fileAttachment" or not content_bytes:
                yield self.create_text_message(
                    f"'{name}' is a {odata_type or 'non-file'} attachment and has no downloadable "
                    "file. Only file attachments (e.g. PDF, Excel, TXT) can be downloaded."
                )
                yield self.create_json_message(attachment)
                return

            try:
                raw = base64.b64decode(content_bytes)
            except Exception:
                yield self.create_text_message("Failed to decode the attachment content.")
                return

            yield self.create_text_message(f"Downloaded attachment: {name}")
            yield self.create_blob_message(
                blob=raw,
                meta={"mime_type": content_type, "filename": name},
            )

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
