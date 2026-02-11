import base64
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DownloadAttachmentTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Download an attachment from a Gmail message.

        Returns the attachment content as base64-encoded data along with metadata.
        To use this tool, you first need to call get_message with include_attachments=True
        to get the message_id and attachment_id.
        """
        try:
            # Get parameters
            message_id = tool_parameters.get("message_id", "").strip()
            attachment_id = tool_parameters.get("attachment_id", "").strip()

            if not message_id:
                yield self.create_text_message("Error: Message ID is required.")
                return

            if not attachment_id:
                yield self.create_text_message("Error: Attachment ID is required.")
                return

            # Get credentials from tool provider
            access_token = self.runtime.credentials.get("access_token")

            if not access_token:
                yield self.create_text_message("Error: No access token available. Please authorize the Gmail integration.")
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }

            # Download attachment
            attachment_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}"

            yield self.create_text_message(f"Downloading attachment from message {message_id}...")

            attachment_response = requests.get(attachment_url, headers=headers, timeout=60)

            if attachment_response.status_code == 401:
                yield self.create_text_message("Error: Access token expired. Please re-authorize the Gmail integration.")
                return
            elif attachment_response.status_code == 404:
                yield self.create_text_message("Error: Attachment not found. The message ID or attachment ID may be invalid.")
                return
            elif attachment_response.status_code != 200:
                yield self.create_text_message(f"Error: Gmail API returned status {attachment_response.status_code}")
                return

            attachment_data = attachment_response.json()

            # Gmail returns attachments with base64url-encoded data
            encoded_data = attachment_data.get("data")
            size_bytes = attachment_data.get("size", 0)

            if not encoded_data:
                yield self.create_text_message("Error: No attachment data received from Gmail API.")
                return

            # Decode the attachment content
            try:
                decoded_bytes = self._decode_base64url(encoded_data)
            except ValueError as e:
                yield self.create_text_message(f"Error decoding attachment data: {e}")
                return

            # Check size limit (25MB is Gmail's practical attachment limit)
            MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024
            if size_bytes > MAX_ATTACHMENT_SIZE_BYTES:
                yield self.create_text_message(
                    f"Warning: Attachment size ({size_bytes} bytes) exceeds 25MB. "
                    "This may cause issues with some operations."
                )

            # Re-encode as standard base64 for output
            content_base64 = base64.b64encode(decoded_bytes).decode("utf-8")

            # Create output
            yield self.create_text_message(
                f"Successfully downloaded attachment ({size_bytes} bytes)."
            )

            yield self.create_variable_message("attachment_data", content_base64)
            yield self.create_variable_message("attachment_size", str(size_bytes))

            yield self.create_json_message({
                "status": "success",
                "message_id": message_id,
                "attachment_id": attachment_id,
                "size": size_bytes,
                "data": content_base64,
                "encoding": "base64"
            })

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error downloading attachment: {str(e)}")

    def _decode_base64url(self, data: str) -> bytes:
        """
        Decode base64url encoded string to bytes.

        Gmail uses base64url encoding (RFC 4648) where:
        - '+' is replaced with '-'
        - '/' is replaced with '_'
        - Padding '=' may be omitted
        """
        try:
            # Use Python's built-in base64url decoder
            # Add padding if needed
            missing_padding = len(data) % 4
            if missing_padding:
                data += "=" * (4 - missing_padding)

            return base64.urlsafe_b64decode(data)
        except (binascii.Error, TypeError) as e:
            raise ValueError(f"Failed to decode base64url data: {e}") from e
