from collections.abc import Generator
from typing import Any
import requests
import msal
from datetime import datetime

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListDraftEmailsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List draft emails using Microsoft Graph API
        """
        try:
            # Get parameters
            user_email = self.runtime.credentials.get("user_email")
            limit = int(tool_parameters.get("limit", 10))
            search_query = tool_parameters.get("search", "")
            include_attachments_info = tool_parameters.get("include_attachments_info", True)
            
            # Validate parameters
            if not user_email:
                yield self.create_text_message("User email is required in credentials.")
                return
                
            if limit < 1 or limit > 100:
                yield self.create_text_message("Limit must be between 1 and 100.")
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
                
                # Get draft emails
                drafts = self._get_draft_emails(access_token, user_email, limit, search_query, include_attachments_info)
                
                if isinstance(drafts, str):  # Error message
                    yield self.create_text_message(drafts)
                    return
                
                # Format and return results
                if not drafts:
                    summary = "No draft emails found"
                    if search_query:
                        summary += f" matching '{search_query}'"
                    yield self.create_text_message(summary)
                    return
                
                # Create summary
                summary = f"Found {len(drafts)} draft emails for {user_email}"
                if search_query:
                    summary += f" matching '{search_query}'"
                
                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "total_count": len(drafts),
                    "user_email": user_email,
                    "search_query": search_query if search_query else None,
                    "drafts": drafts
                })
                
            except Exception as e:
                yield self.create_text_message(f"Error accessing draft emails: {str(e)}")
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
    
    def _get_draft_emails(self, access_token: str, user_email: str, limit: int, 
                         search_query: str, include_attachments_info: bool):
        """
        Get draft emails from Microsoft Graph API
        """
        try:
            # Build base URL for drafts folder
            base_url = f"https://graph.microsoft.com/v1.0/users/{user_email}/mailFolders/drafts/messages"
            
            # Build select fields
            select_fields = [
                "id", "subject", "sender", "toRecipients", "ccRecipients", 
                "createdDateTime", "lastModifiedDateTime", "bodyPreview", 
                "hasAttachments", "importance", "conversationId", "isDraft"
            ]
            
            # Build query parameters
            params = {
                "$top": limit,
                "$select": ",".join(select_fields),
                "$orderby": "lastModifiedDateTime desc"
            }
            
            # Add search if specified
            if search_query:
                params["$search"] = f'"{search_query}"'
            
            # Set headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "ConsistencyLevel": "eventual"  # Required for search
            }
            
            # Make API request
            response = requests.get(base_url, headers=headers, params=params, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                return "Authentication failed. Token may be expired."
            elif response.status_code == 403:
                return "Access denied. Check app permissions and admin consent."
            elif response.status_code == 404:
                return f"User '{user_email}' not found or drafts folder not accessible."
            elif response.status_code != 200:
                return f"API error {response.status_code}: {response.text}"
            
            data = response.json()
            messages = data.get("value", [])
            
            # Format messages
            formatted_drafts = []
            for msg in messages:
                draft_data = self._format_draft_email(msg, include_attachments_info, access_token, user_email)
                formatted_drafts.append(draft_data)
            
            return formatted_drafts
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error fetching draft emails: {str(e)}"
    
    def _format_draft_email(self, msg: dict, include_attachments_info: bool, 
                           access_token: str = None, user_email: str = None) -> dict:
        """
        Format draft email message data
        """
        # Parse datetime
        created_dt = msg.get("createdDateTime", "")
        modified_dt = msg.get("lastModifiedDateTime", "")
        
        created_str = self._format_datetime(created_dt)
        modified_str = self._format_datetime(modified_dt)
        
        # Get recipients
        to_recipients = [
            self._extract_email_address(recipient) 
            for recipient in msg.get("toRecipients", [])
        ]
        
        cc_recipients = [
            self._extract_email_address(recipient) 
            for recipient in msg.get("ccRecipients", [])
        ]
        
        # Format preview
        preview = msg.get("bodyPreview", "No preview available")
        if len(preview) > 300:
            preview = preview[:300] + "..."
        
        # Build draft data
        draft_data = {
            "id": msg.get("id", ""),
            "subject": msg.get("subject", "No Subject"),
            "to_recipients": to_recipients,
            "cc_recipients": cc_recipients,
            "created_datetime": created_str,
            "last_modified_datetime": modified_str,
            "preview": preview,
            "has_attachments": msg.get("hasAttachments", False),
            "importance": msg.get("importance", "normal"),
            "conversation_id": msg.get("conversationId", ""),
            "is_draft": msg.get("isDraft", True)
        }
        
        # Get attachment details if requested and attachments exist
        if include_attachments_info and msg.get("hasAttachments", False) and access_token and user_email:
            attachments_info = self._get_attachment_details(access_token, user_email, msg.get("id", ""))
            draft_data["attachments"] = attachments_info
        else:
            draft_data["attachments"] = []
        
        return draft_data
    
    def _get_attachment_details(self, access_token: str, user_email: str, message_id: str) -> list:
        """
        Get attachment details for a message
        """
        try:
            url = f"https://graph.microsoft.com/v1.0/users/{user_email}/messages/{message_id}/attachments"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            params = {
                "$select": "id,name,contentType,size,lastModifiedDateTime,isInline"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                attachments = []
                
                for attachment in data.get("value", []):
                    attachments.append({
                        "id": attachment.get("id", ""),
                        "name": attachment.get("name", "Unknown"),
                        "content_type": attachment.get("contentType", "unknown"),
                        "size": attachment.get("size", 0),
                        "last_modified": self._format_datetime(attachment.get("lastModifiedDateTime", "")),
                        "is_inline": attachment.get("isInline", False)
                    })
                
                return attachments
            else:
                return []
                
        except Exception as e:
            print(f"Error getting attachment details: {str(e)}")
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
    
    def _format_datetime(self, dt_string: str) -> str:
        """
        Format datetime string
        """
        if not dt_string:
            return "Unknown"
        
        try:
            dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            return dt_string