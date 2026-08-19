from collections.abc import Generator
from typing import Any
import base64
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Send an email message directly through Outlook using Microsoft Graph API
        """
        try:
            # Get parameters
            to_recipients = tool_parameters.get("to", "")
            subject = tool_parameters.get("subject", "")
            message = tool_parameters.get("message", "")
            attachments = tool_parameters.get("attachments")  # optional list of files

            # Validate required parameters
            if not to_recipients:
                yield self.create_text_message("To recipients are required.")
                return

            if not subject:
                yield self.create_text_message("Subject is required.")
                return

            if not message:
                yield self.create_text_message("Message content is required.")
                return

            # Get access token from OAuth credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Access token is required in credentials.")
                return

            try:
                # Send the email directly
                result = self._send_message(access_token, to_recipients, subject, message, attachments)

                if isinstance(result, str):  # Error message
                    yield self.create_text_message(result)
                    return

                # Success
                attach_note = f" with {result.get('attachment_count', 0)} attachment(s)" if result.get("attachment_count") else ""
                yield self.create_text_message(f"Message sent successfully: {subject}{attach_note}")
                yield self.create_json_message({
                    "status": "sent",
                    "subject": subject,
                    "to_recipients": self._parse_recipients(to_recipients),
                    "attachment_count": result.get("attachment_count", 0),
                })

            except Exception as e:
                yield self.create_text_message(f"Error sending message: {str(e)}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

    def _build_attachments(self, attachments) -> list:
        """
        Convert Dify file objects into Microsoft Graph fileAttachment entries.

        Note: sendMail carries attachments inline (base64) in the request, so the
        total size should stay small (a few MB). For larger files, use the draft
        flow (draft_message -> add_attachment_to_draft -> send_draft).
        """
        graph_attachments = []
        for file_obj in (attachments or []):
            content = file_obj.blob
            if isinstance(content, str):
                content = content.encode("utf-8")
            name = file_obj.filename or "attachment"
            extension = getattr(file_obj, "extension", None)
            if extension and not name.endswith(extension):
                name += extension
            graph_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentBytes": base64.b64encode(content).decode("utf-8"),
            })
        return graph_attachments

    def _send_message(self, access_token: str, to_recipients: str, subject: str, message: str, attachments=None):
        """
        Send an email message using Microsoft Graph API
        """
        try:
            # Parse recipients
            recipient_list = self._parse_recipients(to_recipients)

            # Prepare message body
            graph_message: dict[str, Any] = {
                "subject": subject,
                "body": {
                    "contentType": "text",
                    "content": message
                },
                "toRecipients": [
                    {"emailAddress": {"address": email.strip()}}
                    for email in recipient_list
                ]
            }

            graph_attachments = self._build_attachments(attachments)
            if graph_attachments:
                graph_message["attachments"] = graph_attachments

            message_body = {"message": graph_message}

            # API endpoint
            url = "https://graph.microsoft.com/v1.0/me/sendMail"

            # Headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # Make API request
            response = requests.post(url, headers=headers, json=message_body, timeout=60)

            # Handle response
            if response.status_code == 401:
                return "Authentication failed. Token may be expired."
            elif response.status_code == 403:
                return "Access denied. Check app permissions (Mail.Send required)."
            elif response.status_code == 400:
                return f"Bad request: {response.text}"
            elif response.status_code != 202:
                return f"API error {response.status_code}: {response.text}"

            # For sendMail endpoint, successful response is 202 with empty body
            return {
                "status": "sent",
                "attachment_count": len(graph_attachments),
            }

        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error sending message: {str(e)}"

    def _parse_recipients(self, recipients_str: str) -> list:
        """
        Parse comma-separated email addresses
        """
        if not recipients_str:
            return []

        # Split by comma and clean up whitespace
        recipients = [email.strip() for email in recipients_str.split(",")]
        # Filter out empty strings
        recipients = [email for email in recipients if email]

        return recipients
