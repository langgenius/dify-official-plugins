from collections.abc import Generator
from typing import Any, List, Dict
import requests
import msal
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DraftEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a draft email using Microsoft Graph API
        """
        try:
            # Get parameters
            user_email = self.runtime.credentials.get("user_email")
            to_recipients = tool_parameters.get("to_recipients", "")
            cc_recipients = tool_parameters.get("cc_recipients", "")
            bcc_recipients = tool_parameters.get("bcc_recipients", "")
            subject = tool_parameters.get("subject", "")
            body_content = tool_parameters.get("body", "")
            body_type = tool_parameters.get("body_type", "text")  # text or html
            importance = tool_parameters.get("importance", "normal")  # low, normal, high
            
            # Validate required parameters
            if not user_email:
                yield self.create_text_message("User email is required in credentials.")
                return
                
            if not to_recipients:
                yield self.create_text_message("To recipients are required.")
                return
            
            if not subject:
                yield self.create_text_message("Subject is required.")
                return
            
            if not body_content:
                yield self.create_text_message("Email body is required.")
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
                
                # Create draft email
                result = self._create_draft_email(
                    access_token, user_email, to_recipients, cc_recipients, bcc_recipients,
                    subject, body_content, body_type, importance
                )
                
                if isinstance(result, str):  # Error message
                    yield self.create_text_message(result)
                    return
                
                # Success: return only the draft_id as a text message
                draft_id = result.get("id")
                if draft_id:
                    yield self.create_text_message(draft_id)
                else:
                    yield self.create_text_message("Draft created but no ID returned.")
                return
                
            except Exception as e:
                yield self.create_text_message(f"Error creating draft email: {str(e)}")
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
    
    def _create_draft_email(self, access_token: str, user_email: str, to_recipients: str,
                           cc_recipients: str, bcc_recipients: str, subject: str,
                           body_content: str, body_type: str, importance: str):
        """
        Create a draft email using Microsoft Graph API
        """
        try:
            # Parse recipients
            to_list = self._parse_recipients(to_recipients)
            cc_list = self._parse_recipients(cc_recipients) if cc_recipients else []
            bcc_list = self._parse_recipients(bcc_recipients) if bcc_recipients else []
            
            if not to_list:
                return "Invalid to recipients format. Use: email1@domain.com, email2@domain.com"
            
            # Build email message object
            message = {
                "subject": subject,
                "importance": importance,
                "body": {
                    "contentType": "html" if body_type.lower() == "html" else "text",
                    "content": body_content
                },
                "toRecipients": to_list
            }
            
            # Add CC recipients if provided
            if cc_list:
                message["ccRecipients"] = cc_list
            
            # Add BCC recipients if provided
            if bcc_list:
                message["bccRecipients"] = bcc_list
            
            # API endpoint
            url = f"https://graph.microsoft.com/v1.0/users/{user_email}/messages"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Make API request
            response = requests.post(url, headers=headers, json=message, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                return "Authentication failed. Token may be expired."
            elif response.status_code == 403:
                return "Access denied. Check app permissions (Mail.ReadWrite required)."
            elif response.status_code == 404:
                return f"User '{user_email}' not found."
            elif response.status_code not in [200, 201]:
                return f"API error {response.status_code}: {response.text}"
            
            # Parse response
            draft_data = response.json()
            
            # Format response
            result = {
                "id": draft_data.get("id"),
                "subject": draft_data.get("subject"),
                "created_datetime": draft_data.get("createdDateTime"),
                "sender": user_email,
                "to_recipients": [self._format_recipient(r) for r in draft_data.get("toRecipients", [])],
                "cc_recipients": [self._format_recipient(r) for r in draft_data.get("ccRecipients", [])],
                "bcc_recipients": [self._format_recipient(r) for r in draft_data.get("bccRecipients", [])],
                "importance": draft_data.get("importance"),
                "body_preview": draft_data.get("bodyPreview", "")[:200] + "..." if len(draft_data.get("bodyPreview", "")) > 200 else draft_data.get("bodyPreview", ""),
                "web_link": draft_data.get("webLink"),
                "conversation_id": draft_data.get("conversationId")
            }
            
            return result
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error creating draft: {str(e)}"
    
    def _parse_recipients(self, recipients_str: str) -> List[Dict]:
        """
        Parse recipients string into Graph API format
        """
        if not recipients_str:
            return []
        
        recipients = []
        
        # Split by comma and clean up
        email_list = [email.strip() for email in recipients_str.split(",")]
        
        for email in email_list:
            if not email:
                continue
            
            # Check if it's in "Name <email@domain.com>" format
            if "<" in email and ">" in email:
                # Extract name and email
                name_part = email.split("<")[0].strip()
                email_part = email.split("<")[1].split(">")[0].strip()
                
                recipients.append({
                    "emailAddress": {
                        "address": email_part,
                        "name": name_part
                    }
                })
            else:
                # Just email address
                recipients.append({
                    "emailAddress": {
                        "address": email,
                        "name": email
                    }
                })
        
        return recipients
    
    def _format_recipient(self, recipient: Dict) -> Dict:
        """
        Format recipient for response
        """
        email_address = recipient.get("emailAddress", {})
        return {
            "name": email_address.get("name", "Unknown"),
            "email": email_address.get("address", "Unknown")
        }