import base64
import email
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DraftMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # Get parameters
            to_recipients = tool_parameters.get("to", "").strip()
            subject = tool_parameters.get("subject", "").strip()
            body = tool_parameters.get("body", "").strip()
            cc_recipients = tool_parameters.get("cc", "").strip()
            bcc_recipients = tool_parameters.get("bcc", "").strip()
            reply_to = tool_parameters.get("reply_to", "").strip()
            
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
                "message": {
                    "raw": encoded_message
                }
            }
            
            yield self.create_text_message("Creating draft email...")
            
            # Create the draft
            draft_url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
            
            response = requests.post(
                draft_url,
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
            draft_id = response_data.get("id")
            message_id = response_data.get("message", {}).get("id")
            thread_id = response_data.get("message", {}).get("threadId")
            
            if not draft_id:
                yield self.create_text_message("Error: Failed to create draft. No draft ID received.")
                return
            
            # Return success results
            yield self.create_text_message("Draft email created successfully!")
            
            # Create specific output variables for workflow referencing
            yield self.create_variable_message("draft_id", draft_id)
            yield self.create_variable_message("message_id", message_id)
            yield self.create_variable_message("thread_id", thread_id)
            
            yield self.create_json_message({
                "status": "success",
                "draft_id": draft_id,
                "message_id": message_id,
                "thread_id": thread_id,
                "to": to_recipients if to_recipients else None,
                "subject": subject if subject else None,
                "body": body if body else None,
                "cc": cc_recipients if cc_recipients else None,
                "bcc": bcc_recipients if bcc_recipients else None,
                "reply_to": reply_to if reply_to else None
            })
            
        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error creating draft: {str(e)}")
    
    def _create_email_message(self, to_recipients: str, subject: str, body: str, 
                             cc_recipients: str, bcc_recipients: str, reply_to: str) -> str:
        """Create a properly formatted email message"""
        try:
            # Create email message
            msg = email.message.EmailMessage()
            
            # Set basic headers (only if provided)
            if to_recipients:
                msg["To"] = to_recipients
            
            if subject:
                msg["Subject"] = subject
            
            # Set optional headers
            if cc_recipients:
                msg["Cc"] = cc_recipients
            
            if bcc_recipients:
                msg["Bcc"] = bcc_recipients
            
            if reply_to:
                msg["Reply-To"] = reply_to
            
            # Set content type and body (only if provided)
            if body:
                msg.set_content(body, subtype="plain")
            else:
                # Set empty content for empty drafts
                msg.set_content("", subtype="plain")
            
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