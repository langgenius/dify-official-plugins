from collections.abc import Generator
from typing import Any
import requests
from datetime import datetime

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListEmailsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List emails from Outlook using Microsoft Graph API
        """
        try:
            # Get parameters
            limit = int(tool_parameters.get("limit", 10))
            folder = tool_parameters.get("folder", "inbox")
            search_query = tool_parameters.get("search", "")
            include_body = tool_parameters.get("include_body", False)
            
            # Validate parameters
            if limit < 1 or limit > 100:
                yield self.create_text_message("Limit must be between 1 and 100.")
                return
                
            # Get access token from OAuth credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Access token is required in credentials.")
                return
            
            try:
                # Get emails
                emails = self._get_emails(access_token, limit, folder, search_query, include_body)
                
                if isinstance(emails, str):  # Error message
                    yield self.create_text_message(emails)
                    return
                
                # Format and return results
                if not emails:
                    summary = f"No emails found in {folder}"
                    if search_query:
                        summary += f" matching '{search_query}'"
                    yield self.create_text_message(summary)
                    return
                
                # Create summary
                summary = f"Found {len(emails)} emails in {folder}"
                if search_query:
                    summary += f" matching '{search_query}'"
                
                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "total_count": len(emails),
                    "folder": folder,
                    "search_query": search_query if search_query else None,
                    "emails": emails
                })
                
            except Exception as e:
                yield self.create_text_message(f"Error accessing emails: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
    
    def _get_emails(self, access_token: str, limit: int, 
                   folder: str, search_query: str, include_body: bool):
        """
        Get emails from Microsoft Graph API
        """
        try:
            # Build base URL using /me
            if folder.lower() == "inbox":
                base_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
            elif folder.lower() == "sent":
                base_url = "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages"
            elif folder.lower() == "drafts":
                base_url = "https://graph.microsoft.com/v1.0/me/mailFolders/drafts/messages"
            else:
                # For custom folders, search all messages
                base_url = "https://graph.microsoft.com/v1.0/me/messages"
            
            # Build select fields
            select_fields = [
                "id", "subject", "sender", "toRecipients", "ccRecipients", 
                "receivedDateTime", "sentDateTime", "bodyPreview", 
                "isRead", "hasAttachments", "importance", "conversationId"
            ]
            
            if include_body:
                select_fields.append("body")
            
            # Build query parameters
            params = {
                "$top": limit,
                "$select": ",".join(select_fields)
            }
            
            # Add search if specified
            if search_query:
                params["$search"] = f'"{search_query}"'
            else:
                # Only add orderby when not searching
                params["$orderby"] = "receivedDateTime desc"
            
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
                return f"Folder '{folder}' not found."
            elif response.status_code != 200:
                return f"API error {response.status_code}: {response.text}"
            
            data = response.json()
            messages = data.get("value", [])
            
            # Format messages
            formatted_emails = []
            for msg in messages:
                email_data = self._format_email(msg, include_body)
                formatted_emails.append(email_data)
            
            return formatted_emails
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error fetching emails: {str(e)}"
    
    def _format_email(self, msg: dict, include_body: bool = False) -> dict:
        """
        Format email message data
        """
        # Parse datetime
        received_dt = msg.get("receivedDateTime", "")
        sent_dt = msg.get("sentDateTime", "")
        
        received_str = self._format_datetime(received_dt)
        sent_str = self._format_datetime(sent_dt)
        
        # Get sender info
        sender_info = msg.get("sender", {})
        sender_data = self._extract_email_address(sender_info)
        
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
        
        # Build email data
        email_data = {
            "id": msg.get("id", ""),
            "subject": msg.get("subject", "No Subject"),
            "sender": sender_data,
            "to_recipients": to_recipients,
            "cc_recipients": cc_recipients,
            "received_datetime": received_str,
            "sent_datetime": sent_str,
            "preview": preview,
            "is_read": msg.get("isRead", False),
            "has_attachments": msg.get("hasAttachments", False),
            "importance": msg.get("importance", "normal"),
            "conversation_id": msg.get("conversationId", "")
        }
        
        # Include full body if requested
        if include_body and "body" in msg:
            body_content = msg["body"]
            email_data["body"] = {
                "content_type": body_content.get("contentType", "text"),
                "content": body_content.get("content", "")
            }
        
        return email_data
    
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