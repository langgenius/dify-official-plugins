import base64
import email
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # Get parameters
            to_recipients = tool_parameters.get("to", "").strip()
            subject = tool_parameters.get("subject", "").strip()
            body = tool_parameters.get("body", "").strip()
            cc_recipients = tool_parameters.get("cc", "").strip()
            bcc_recipients = tool_parameters.get("bcc", "").strip()
            reply_to = tool_parameters.get("reply_to", "").strip()
            
            # Validate required parameters
            if not to_recipients:
                yield self.create_text_message("Error: 'To' recipients are required.")
                return
            
            if not subject:
                yield self.create_text_message("Error: Subject is required.")
                return
            
            if not body:
                yield self.create_text_message("Error: Email body is required.")
                return
            
            # Get credentials from tool provider
            access_token = self.runtime.credentials.get("access_token")
            
            if not access_token:
                yield self.create_text_message("Error: No access token available. Please authorize the Gmail integration.")
                return
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            # Create the email message
            email_message = self._create_email_message(
                to_recipients, subject, body, cc_recipients, bcc_recipients, reply_to
            )
            
            # Encode the message
            encoded_message = base64.urlsafe_b64encode(email_message.encode()).decode()
            
            # Prepare the request body
            request_body = {
                "raw": encoded_message
            }
            
            yield self.create_text_message("Sending email...")
            
            # Send the message
            send_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
            
            response = requests.post(
                send_url,
                headers=headers,
                json=request_body,
                timeout=30
            )
            
            if response.status_code == 401:
                yield self.create_text_message("Error: Access token expired. Please re-authorize the Gmail integration.")
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Error: Gmail API returned status {response.status_code}: {response.text}")
                return
            
            # Parse response
            response_data = response.json()
            message_id = response_data.get("id")
            thread_id = response_data.get("threadId")
            
            if not message_id:
                yield self.create_text_message("Error: Failed to send email. No message ID received.")
                return
            
            # Return success results
            yield self.create_text_message("Email sent successfully!")
            
            # Create specific output variables for workflow referencing
            yield self.create_variable_message("message_id", message_id)
            yield self.create_variable_message("thread_id", thread_id)
            
            yield self.create_json_message({
                "status": "success",
                "message_id": message_id,
                "thread_id": thread_id,
                "to": to_recipients,
                "subject": subject,
                "cc": cc_recipients if cc_recipients else None,
                "bcc": bcc_recipients if bcc_recipients else None,
                "reply_to": reply_to if reply_to else None
            })
            
        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error sending message: {str(e)}")
    
    def _create_email_message(self, to_recipients: str, subject: str, body: str, 
                             cc_recipients: str, bcc_recipients: str, reply_to: str) -> str:
        """Create a properly formatted email message"""
        try:
            # Create email message
            msg = email.message.EmailMessage()
            
            # Set basic headers
            msg["To"] = to_recipients
            msg["Subject"] = subject
            
            # Set optional headers
            if cc_recipients:
                msg["Cc"] = cc_recipients
            
            if bcc_recipients:
                msg["Bcc"] = bcc_recipients
            
            if reply_to:
                msg["Reply-To"] = reply_to
            
            # Set content type and body
            msg.set_content(body, subtype="plain")
            
            # Convert to string
            return msg.as_string()
            
        except Exception as e:
            raise Exception(f"Failed to create email message: {str(e)}")
    
    def _validate_email_addresses(self, email_string: str) -> bool:
        """Basic email address validation"""
        if not email_string:
            return True
        
        # Simple validation - check for @ symbol and basic format
        addresses = [addr.strip() for addr in email_string.split(",")]
        
        for address in addresses:
            if not address or "@" not in address or "." not in address:
                return False
        
        return True 