from collections.abc import Generator
from typing import Any
import requests
import msal

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class PrioritizeEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Set the priority/importance level of an email using Microsoft Graph API
        """
        try:
            # Get parameters
            user_email = self.runtime.credentials.get("user_email")
            email_id = tool_parameters.get("email_id", "")
            priority_level = tool_parameters.get("priority_level", "normal")
            
            # Validate required parameters
            if not user_email:
                yield self.create_text_message("User email is required in credentials.")
                return
                
            if not email_id:
                yield self.create_text_message("Email ID is required.")
                return
            
            if priority_level not in ["low", "normal", "high"]:
                yield self.create_text_message("Priority level must be 'low', 'normal', or 'high'.")
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
                
                # Update email priority
                result = self._update_email_priority(access_token, user_email, email_id, priority_level)
                
                if isinstance(result, str):  # Error message
                    yield self.create_text_message(result)
                    return
                
                # Success
                yield self.create_text_message(f"Email priority updated to '{priority_level}' successfully!")
                yield self.create_json_message(result)
                
            except Exception as e:
                yield self.create_text_message(f"Error updating email priority: {str(e)}")
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
    
    def _update_email_priority(self, access_token: str, user_email: str, email_id: str, priority_level: str):
        """
        Update email priority using Microsoft Graph API
        """
        try:
            # Build the update payload
            update_data = {
                "importance": priority_level
            }
            
            # API endpoint
            url = f"https://graph.microsoft.com/v1.0/users/{user_email}/messages/{email_id}"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Make PATCH request to update the email
            response = requests.patch(url, headers=headers, json=update_data, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                return "Authentication failed. Token may be expired."
            elif response.status_code == 403:
                return "Access denied. Check app permissions (Mail.ReadWrite required)."
            elif response.status_code == 404:
                return f"Email with ID '{email_id}' not found."
            elif response.status_code not in [200, 204]:
                return f"API error {response.status_code}: {response.text}"
            
            # Get updated email details
            get_response = requests.get(
                f"{url}?$select=id,subject,importance,sender,receivedDateTime",
                headers=headers,
                timeout=30
            )
            
            if get_response.status_code == 200:
                email_data = get_response.json()
                
                # Format response
                result = {
                    "email_id": email_data.get("id"),
                    "subject": email_data.get("subject"),
                    "new_priority": email_data.get("importance"),
                    "sender": self._extract_sender_info(email_data.get("sender", {})),
                    "received_datetime": email_data.get("receivedDateTime"),
                    "update_successful": True
                }
                
                return result
            else:
                # Update was successful but couldn't retrieve updated details
                return {
                    "email_id": email_id,
                    "new_priority": priority_level,
                    "update_successful": True,
                    "note": "Priority updated successfully but couldn't retrieve updated details"
                }
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error updating email priority: {str(e)}"
    
    def _extract_sender_info(self, sender_obj: dict) -> dict:
        """
        Extract sender information
        """
        if not sender_obj or "emailAddress" not in sender_obj:
            return {"name": "Unknown", "email": "Unknown"}
        
        email_address = sender_obj["emailAddress"]
        return {
            "name": email_address.get("name", "Unknown"),
            "email": email_address.get("address", "Unknown")
        }