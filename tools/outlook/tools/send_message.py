from collections.abc import Generator
from typing import Any
import requests
import json

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
                result = self._send_message(access_token, to_recipients, subject, message)
                
                if isinstance(result, str):  # Error message
                    yield self.create_text_message(result)
                    return
                
                # Success
                yield self.create_text_message(f"Message sent successfully: {subject}")
                yield self.create_json_message({
                    "status": "sent",
                    "message_id": result.get("id"),
                    "subject": subject,
                    "to_recipients": self._parse_recipients(to_recipients),
                    "sent_datetime": result.get("sentDateTime")
                })
                
            except Exception as e:
                yield self.create_text_message(f"Error sending message: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
    
    def _send_message(self, access_token: str, to_recipients: str, subject: str, message: str):
        """
        Send an email message using Microsoft Graph API
        """
        try:
            # Parse recipients
            recipient_list = self._parse_recipients(to_recipients)
            
            # Prepare message body
            message_body = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "text",
                        "content": message
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": email.strip()
                            }
                        }
                        for email in recipient_list
                    ]
                }
            }
            
            # API endpoint
            url = "https://graph.microsoft.com/v1.0/me/sendMail"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Make API request
            response = requests.post(url, headers=headers, json=message_body, timeout=30)
            
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
            # Return a success indicator with basic info
            return {
                "id": None,  # sendMail doesn't return message ID
                "sentDateTime": None,  # Not available from sendMail response
                "status": "sent"
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
