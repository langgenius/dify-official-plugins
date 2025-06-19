from collections.abc import Generator
from typing import Any
import requests
import msal

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Send a draft message through Outlook using Microsoft Graph API
        This tool works with drafts created by the draft_message tool
        """
        try:
            # Get parameters
            user_email = self.runtime.credentials.get("user_email")
            draft_id = tool_parameters.get("draft_id")
            
            # Validate parameters
            if not user_email:
                yield self.create_text_message("User email is required in credentials.")
                return
                
            if not draft_id:
                yield self.create_text_message("Draft ID is required.")
                return
                
            # Get credentials
            client_id = self.runtime.credentials.get("client_id")
            client_secret = self.runtime.credentials.get("client_secret")
            tenant_id = self.runtime.credentials.get("tenant_id")
            
            if not all([client_id, client_secret, tenant_id]):
                yield self.create_text_message("Azure AD credentials are required.")
                return
            
            try:
                # Get access token
                access_token = self._get_access_token(client_id, client_secret, tenant_id)
                if not access_token:
                    yield self.create_text_message("Failed to acquire access token.")
                    return
                
                # Get draft details first
                draft_details = self._get_draft_details(access_token, user_email, draft_id)
                if isinstance(draft_details, str):  # Error message
                    yield self.create_text_message(draft_details)
                    return
                
                # Send the draft
                send_result = self._send_draft(access_token, user_email, draft_id)
                if isinstance(send_result, str):  # Error message
                    yield self.create_text_message(send_result)
                    return
                
                # Success
                yield self.create_text_message(f"Message sent successfully: {draft_details['subject']}")
                yield self.create_json_message({
                    "status": "sent",
                    "draft_id": draft_id,
                    "subject": draft_details["subject"],
                    "to_recipients": draft_details["to_recipients"],
                    "cc_recipients": draft_details["cc_recipients"],
                    "bcc_recipients": draft_details.get("bcc_recipients", []),
                    "body_type": draft_details["body_type"],
                    "importance": draft_details.get("importance", "normal"),
                    "sent_datetime": send_result.get("sent_datetime")
                })
                
            except Exception as e:
                yield self.create_text_message(f"Error sending message: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
    
    def _get_access_token(self, client_id: str, client_secret: str, tenant_id: str) -> str:
        """
        Get access token using client credentials flow
        """
        try:
            app = msal.ConfidentialClientApplication(
                client_id=client_id,
                client_credential=client_secret,
                authority=f"https://login.microsoftonline.com/{tenant_id}"
            )
            
            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            
            if "access_token" in result:
                return result["access_token"]
            else:
                error_desc = result.get("error_description", "Unknown error")
                print(f"Token acquisition failed: {error_desc}")
                return None
                
        except Exception as e:
            print(f"Error getting access token: {str(e)}")
            return None
    
    def _get_draft_details(self, access_token: str, user_email: str, draft_id: str):
        """
        Get details of a draft message
        """
        try:
            url = f"https://graph.microsoft.com/v1.0/users/{user_email}/messages/{draft_id}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                return "Authentication failed. Token may be expired."
            elif response.status_code == 403:
                return "Access denied. Check app permissions (Mail.Read required)."
            elif response.status_code == 404:
                return f"Draft with ID '{draft_id}' not found."
            elif response.status_code != 200:
                return f"API error {response.status_code}: {response.text}"
            
            draft_data = response.json()
            
            # Format response
            return {
                "id": draft_data.get("id"),
                "subject": draft_data.get("subject", "No Subject"),
                "to_recipients": [self._format_recipient(r) for r in draft_data.get("toRecipients", [])],
                "cc_recipients": [self._format_recipient(r) for r in draft_data.get("ccRecipients", [])],
                "bcc_recipients": [self._format_recipient(r) for r in draft_data.get("bccRecipients", [])],
                "body_type": draft_data.get("body", {}).get("contentType", "text"),
                "importance": draft_data.get("importance", "normal"),
                "created_datetime": draft_data.get("createdDateTime")
            }
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error getting draft details: {str(e)}"
    
    def _send_draft(self, access_token: str, user_email: str, draft_id: str):
        """
        Send a draft message using Microsoft Graph API
        """
        try:
            # API endpoint
            url = f"https://graph.microsoft.com/v1.0/users/{user_email}/messages/{draft_id}/send"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Make API request
            response = requests.post(url, headers=headers, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                return "Authentication failed. Token may be expired."
            elif response.status_code == 403:
                return "Access denied. Check app permissions (Mail.Send required)."
            elif response.status_code == 404:
                return f"Draft with ID '{draft_id}' not found."
            elif response.status_code not in [200, 202]:
                return f"API error {response.status_code}: {response.text}"
            
            # Get sent message details
            sent_message = self._get_sent_message(access_token, user_email, draft_id)
            
            return {
                "status": "sent",
                "sent_datetime": sent_message.get("sentDateTime") if sent_message else None
            }
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error sending draft: {str(e)}"
    
    def _get_sent_message(self, access_token: str, user_email: str, message_id: str):
        """
        Get details of a sent message
        """
        try:
            url = f"https://graph.microsoft.com/v1.0/users/{user_email}/messages/{message_id}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            print(f"Error getting sent message: {str(e)}")
            return None
    
    def _format_recipient(self, recipient: dict) -> dict:
        """
        Format recipient for response
        """
        email_address = recipient.get("emailAddress", {})
        return {
            "name": email_address.get("name", "Unknown"),
            "email": email_address.get("address", "Unknown")
        } 