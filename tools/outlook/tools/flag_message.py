from collections.abc import Generator
from typing import Any
import requests
import urllib.parse
from datetime import datetime, timedelta

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class FlagEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Flag an email with follow-up status using Microsoft Graph API
        """
        try:
            # Get parameters
            email_id = tool_parameters.get("email_id", "")
            flag_status = tool_parameters.get("flag_status", "flagged")
            due_date_days = tool_parameters.get("due_date_days", 0)
            flag_message = tool_parameters.get("flag_message", "")         
            # Get access token from OAuth credentials
            access_token = self.runtime.credentials.get("access_token")
            
            try:
                # Update email flag
                result = self._update_email_flag(
                    access_token, email_id, flag_status, 
                    due_date_days, flag_message
                )
                
                if isinstance(result, str):  # Error message
                    yield self.create_text_message(result)
                    return
                
                # Success
                action_msg = {
                    "notFlagged": "removed flag from",
                    "flagged": "flagged",
                    "complete": "marked as complete"
                }.get(flag_status, "updated")
                
                yield self.create_text_message(f"Successfully {action_msg} email!")
                yield self.create_json_message(result)
                
            except Exception as e:
                yield self.create_text_message(f"Error updating email flag: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
    
    def _update_email_flag(self, access_token: str, email_id: str, 
                          flag_status: str, due_date_days: int, flag_message: str):
        """
        Update email flag using Microsoft Graph API
        """
        try:
            # URL encode the email ID to handle special characters
            encoded_email_id = urllib.parse.quote(email_id, safe='')
            
            # Build the flag object
            flag_data = {
                "flagStatus": flag_status
            }
            
            # Add due date if flagging and due_date_days is specified
            if flag_status == "flagged" and due_date_days > 0:
                due_date = datetime.utcnow() + timedelta(days=due_date_days)
                flag_data["dueDateTime"] = {
                    "dateTime": due_date.isoformat() + "Z",
                    "timeZone": "UTC"
                }
                
                # Set start date to today
                start_date = datetime.utcnow()
                flag_data["startDateTime"] = {
                    "dateTime": start_date.isoformat() + "Z",
                    "timeZone": "UTC"
                }
            
            # Build the complete update payload
            update_data = {
                "flag": flag_data
            }
            
            # Add custom message if provided (stored in categories for visibility)
            if flag_message and flag_status == "flagged":
                update_data["categories"] = [f"Follow-up: {flag_message}"]
            elif flag_status == "notFlagged":
                # Clear categories when unflagging
                update_data["categories"] = []
            
            # API endpoint using /me
            url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_email_id}"
            
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
                f"{url}?$select=id,subject,flag,categories,sender,receivedDateTime",
                headers=headers,
                timeout=30
            )
            
            if get_response.status_code == 200:
                email_data = get_response.json()
                flag_info = email_data.get("flag", {})
                
                # Format response
                result = {
                    "email_id": email_data.get("id"),
                    "subject": email_data.get("subject"),
                    "flag_status": flag_info.get("flagStatus", "notFlagged"),
                    "due_date": self._format_datetime(flag_info.get("dueDateTime", {}).get("dateTime")),
                    "start_date": self._format_datetime(flag_info.get("startDateTime", {}).get("dateTime")),
                    "categories": email_data.get("categories", []),
                    "sender": self._extract_sender_info(email_data.get("sender", {})),
                    "received_datetime": email_data.get("receivedDateTime"),
                    "update_successful": True
                }
                
                return result
            else:
                # Update was successful but couldn't retrieve updated details
                return {
                    "email_id": email_id,
                    "flag_status": flag_status,
                    "update_successful": True,
                    "note": "Flag updated successfully but couldn't retrieve updated details"
                }
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error updating email flag: {str(e)}"
    
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
    
    def _format_datetime(self, dt_string: str) -> str:
        """
        Format datetime string
        """
        if not dt_string:
            return None
        
        try:
            # Remove 'Z' and parse
            dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            return dt_string