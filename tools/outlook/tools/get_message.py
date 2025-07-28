from collections.abc import Generator
from typing import Any
import requests
import urllib.parse

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class GetMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get a specific message from Outlook
        """
        try:
            # Get parameters
            message_id = tool_parameters.get("message_id")                
            # Get access token from OAuth credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Access token is required in credentials.")
                return
                
            try:
                # Get message using REST API
                message = self._get_message(access_token, message_id)
                
                if not message:
                    yield self.create_text_message("Message not found.")
                    return
                    
                # Create response
                yield self.create_text_message(f"Retrieved message: {message['subject']}")
                yield self.create_json_message(message)
                
            except Exception as e:
                yield self.create_text_message(f"Error retrieving message: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
    
    def _get_message(self, access_token: str, message_id: str):
        """
        Get message using Microsoft Graph REST API
        """
        try:
            # URL encode the message ID to handle special characters
            encoded_message_id = urllib.parse.quote(message_id, safe='')
            
            url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_message_id}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 401:
                raise Exception("Authentication failed. Token may be expired.")
            elif response.status_code == 403:
                raise Exception("Access denied. Check app permissions.")
            elif response.status_code == 404:
                raise Exception("Message not found.")
            elif response.status_code != 200:
                raise Exception(f"API error {response.status_code}: {response.text}")
            
            message_data = response.json()
            
            # Format response
            result = {
                "id": message_data.get("id"),
                "subject": message_data.get("subject"),
                "sender": self._extract_email_address(message_data.get("sender", {})),
                "to_recipients": [self._extract_email_address(r) for r in message_data.get("toRecipients", [])],
                "cc_recipients": [self._extract_email_address(r) for r in message_data.get("ccRecipients", [])],
                "received": message_data.get("receivedDateTime"),
                "body": message_data.get("body", {}).get("content", ""),
                "body_type": message_data.get("body", {}).get("contentType", "text"),
                "has_attachments": message_data.get("hasAttachments", False)
            }
            
            # Get attachments if any
            if message_data.get("hasAttachments", False):
                attachments = self._get_attachments(access_token, message_id)
                result["attachments"] = attachments
            else:
                result["attachments"] = []
                
            return result
            
        except Exception as e:
            raise Exception(f"Error getting message: {str(e)}")
    
    def _get_attachments(self, access_token: str, message_id: str):
        """
        Get attachments for a message
        """
        try:
            # URL encode the message ID to handle special characters
            encoded_message_id = urllib.parse.quote(message_id, safe='')
            
            url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_message_id}/attachments"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return [{
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "content_type": a.get("contentType"),
                    "size": a.get("size")
                } for a in data.get("value", [])]
            else:
                return []
                
        except Exception as e:
            print(f"Error getting attachments: {str(e)}")
            return []
    
    def _extract_email_address(self, email_obj: dict) -> dict:
        """
        Extract email address information
        """
        if not email_obj or "emailAddress" not in email_obj:
            return {"name": "Unknown", "email": "Unknown"}
        
        email_address = email_obj["emailAddress"]
        return {
            "name": email_address.get("name", "Unknown"),
            "email": email_address.get("address", "Unknown")
        } 