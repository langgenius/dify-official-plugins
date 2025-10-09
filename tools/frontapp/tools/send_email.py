import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.invoke_message import InvokeMessage


class SendEmailTool(Tool):
    """
    Tool for sending emails through Front API
    """
    
    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """
        Send an email through Front API
        
        Args:
            tool_parameters: Dictionary containing email parameters
            
        Yields:
            ToolInvokeMessage: Various message types to communicate results
        """
        # 1. PARAMETER EXTRACTION AND VALIDATION
        recipient_email = tool_parameters.get("recipient_email")
        if not recipient_email:
            yield self.create_text_message("Missing required parameter: 'recipient_email'")
            return
            
        subject = tool_parameters.get("subject")
        if not subject:
            yield self.create_text_message("Missing required parameter: 'subject'")
            return
            
        body = tool_parameters.get("body")
        if not body:
            yield self.create_text_message("Missing required parameter: 'body'")
            return
            
        # Optional parameters
        sender_email = tool_parameters.get("sender_email")
        cc_emails = tool_parameters.get("cc_emails", [])
        bcc_emails = tool_parameters.get("bcc_emails", [])
        
        # 2. CREDENTIAL HANDLING
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message("Front API access token is required. Please configure OAuth authentication.")
            return
            
        access_token = self.runtime.credentials.get("access_token")
        
        # 3. LOG THE OPERATION START
        operation_log = self.create_log_message(
            label="Email Sending Started",
            data={
                "recipient": recipient_email,
                "subject": subject,
                "sender": sender_email,
                "cc_count": len(cc_emails),
                "bcc_count": len(bcc_emails)
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS
        )
        yield operation_log
        
        try:
            # 4. PREPARE EMAIL DATA
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Build email payload
            email_data = {
                "to": [recipient_email],
                "subject": subject,
                "body": body,
                "text": body  # Plain text version
            }
            
            # Add optional fields
            if sender_email:
                email_data["sender_name"] = sender_email
                
            if cc_emails:
                email_data["cc"] = cc_emails
                
            if bcc_emails:
                email_data["bcc"] = bcc_emails
            
            # 5. SEND EMAIL VIA FRONT API
            # First, get available channels to find an appropriate one for sending
            channels_response = requests.get(
                "https://api2.frontapp.com/channels",
                headers=headers,
                timeout=30
            )
            
            if channels_response.status_code != 200:
                error_msg = f"Failed to fetch channels: {channels_response.status_code}"
                yield self.create_text_message(error_msg)
                return
                
            channels_data = channels_response.json()
            email_channels = [ch for ch in channels_data.get("_results", []) if ch.get("type") == "smtp"]
            
            if not email_channels:
                yield self.create_text_message("No email channels available. Please configure an email channel in Front.")
                return
                
            # Use the first available email channel
            channel_id = email_channels[0]["id"]
            
            # Create the message payload for Front API
            message_payload = {
                "author_id": email_channels[0].get("id"),
                "to": [recipient_email],
                "subject": subject,
                "body": body,
                "text": body
            }
            
            if cc_emails:
                message_payload["cc"] = cc_emails
                
            if bcc_emails:
                message_payload["bcc"] = bcc_emails
            
            # Send the message
            api_log = self.create_log_message(
                label="API Call - Send Message",
                data={"channel_id": channel_id, "endpoint": f"channels/{channel_id}/outbound_messages"},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                parent=operation_log
            )
            yield api_log
            
            send_response = requests.post(
                f"https://api2.frontapp.com/channels/{channel_id}/outbound_messages",
                headers=headers,
                json=message_payload,
                timeout=30
            )
            
            # 6. HANDLE RESPONSE
            if send_response.status_code in [200, 201, 202]:
                response_data = send_response.json()
                
                yield self.create_json_message(response_data)
                
                message_id = response_data.get("id", "unknown")
                yield self.create_text_message(f"Email sent successfully! Message ID: {message_id}")
                
                # Return structured result
                result = {
                    "success": True,
                    "message_id": message_id,
                    "recipient": recipient_email,
                    "subject": subject,
                    "channel_used": email_channels[0].get("name", "Unknown")
                }
                yield self.create_variable_message("email_result", result)
                
            else:
                # Handle API errors
                error_msg = f"Failed to send email: HTTP {send_response.status_code}"
                try:
                    error_data = send_response.json()
                    error_msg += f" - {error_data.get('message', 'Unknown error')}"
                except:
                    error_msg += f" - {send_response.text}"
                
                yield self.create_log_message(
                    label="Send Email Error",
                    data={
                        "status_code": send_response.status_code,
                        "error": send_response.text[:200]
                    },
                    status=InvokeMessage.LogMessage.LogStatus.ERROR
                )
                yield self.create_text_message(error_msg)
                
        except requests.Timeout:
            yield self.create_text_message("Request timed out. Please try again.")
            
        except requests.RequestException as e:
            yield self.create_log_message(
                label="Network Error",
                data={"error": str(e)},
                status=InvokeMessage.LogMessage.LogStatus.ERROR
            )
            yield self.create_text_message(f"Network error occurred: {str(e)}")
            
        except Exception as e:
            # Handle unexpected errors
            yield self.create_log_message(
                label="Unexpected Error",
                data={"error": str(e), "type": type(e).__name__},
                status=InvokeMessage.LogMessage.LogStatus.ERROR
            )
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")