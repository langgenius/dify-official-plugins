import base64
import html
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # Get parameters
            message_id = tool_parameters.get("message_id")
            include_body = tool_parameters.get("include_body", True)
            include_attachments = tool_parameters.get("include_attachments", False)
            
            if not message_id:
                yield self.create_text_message("Error: Message ID is required.")
                return
            
            # Get credentials from tool provider
            access_token = self.runtime.credentials.get("access_token")
            
            if not access_token:
                yield self.create_text_message("Error: No access token available. Please authorize the Gmail integration.")
                return
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            # Get message details - always use full format for complete message data
            message_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full"
            
            yield self.create_text_message(f"Retrieving details for message {message_id}...")
            
            message_response = requests.get(message_url, headers=headers, timeout=10)
            
            if message_response.status_code == 401:
                yield self.create_text_message("Error: Access token expired. Please re-authorize the Gmail integration.")
                return
            elif message_response.status_code == 404:
                yield self.create_text_message("Error: Message not found. The message ID may be invalid or the message may have been deleted.")
                return
            elif message_response.status_code != 200:
                yield self.create_text_message(f"Error: Gmail API returned status {message_response.status_code}")
                return
            
            message_data = message_response.json()
            
            # Parse the message
            email_info = self._parse_message(message_data, include_body, include_attachments)
            
            if "error" in email_info:
                yield self.create_text_message(f"Error parsing message: {email_info['error']}")
                return
            
            # Return results
            yield self.create_variable_message("message_id", message_id)
            
            yield self.create_json_message({
                "message": email_info,
                "message_id": message_id
            })
            
        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error retrieving message: {str(e)}")
    
    def _parse_message(self, message_data: dict, include_body: bool, include_attachments: bool) -> dict:
        """Parse Gmail message data into a comprehensive format"""
        try:
            payload = message_data.get("payload", {})
            headers = payload.get("headers", [])
            
            # Extract basic message info
            message_info = {
                "id": message_data.get("id"),
                "thread_id": message_data.get("threadId"),
                "labels": message_data.get("labelIds", []),
                "snippet": message_data.get("snippet", ""),
                "history_id": message_data.get("historyId"),
                "internal_date": message_data.get("internalDate"),
                "size_estimate": message_data.get("sizeEstimate"),
                "subject": "",
                "from": "",
                "to": "",
                "cc": "",
                "bcc": "",
                "reply_to": "",
                "date": "",
                "message_id_header": "",
                "references": "",
                "in_reply_to": "",
                "body": "",
                "attachments": [],
                "has_attachments": False,
                "attachment_count": 0
            }
            
            # Parse headers
            for header in headers:
                name = header.get("name", "").lower()
                value = header.get("value", "")
                
                if name == "subject":
                    message_info["subject"] = value
                elif name == "from":
                    message_info["from"] = value
                elif name == "to":
                    message_info["to"] = value
                elif name == "cc":
                    message_info["cc"] = value
                elif name == "bcc":
                    message_info["bcc"] = value
                elif name == "reply-to":
                    message_info["reply_to"] = value
                elif name == "date":
                    message_info["date"] = value
                elif name == "message-id":
                    message_info["message_id_header"] = value
                elif name == "references":
                    message_info["references"] = value
                elif name == "in-reply-to":
                    message_info["in_reply_to"] = value
            
            # Check for attachments
            if "parts" in payload:
                message_info["has_attachments"] = True
                message_info["attachment_count"] = self._count_attachments(payload)
                
                if include_attachments:
                    message_info["attachments"] = self._extract_attachment_info(payload)
            
            # Extract body if requested
            if include_body:
                message_info["body"] = self._extract_body(payload)
            
            return message_info
            
        except Exception as e:
            return {
                "id": message_data.get("id", "unknown"),
                "error": f"Failed to parse message: {str(e)}"
            }
    
    def _count_attachments(self, payload: dict) -> int:
        """Count attachments in message payload"""
        try:
            count = 0
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("filename") and part.get("filename").strip():
                        count += 1
                    elif "parts" in part:
                        count += self._count_attachments(part)
            return count
        except Exception:
            return 0
    
    def _extract_attachment_info(self, payload: dict) -> list:
        """Extract detailed attachment information"""
        try:
            attachments = []
            
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("filename") and part.get("filename").strip():
                        attachment_info = {
                            "filename": part.get("filename", ""),
                            "mime_type": part.get("mimeType", ""),
                            "part_id": part.get("partId", ""),
                            "size": part.get("body", {}).get("size", 0),
                            "attachment_id": part.get("body", {}).get("attachmentId", "")
                        }
                        attachments.append(attachment_info)
                    elif "parts" in part:
                        attachments.extend(self._extract_attachment_info(part))
            
            return attachments
        except Exception:
            return []
    
    def _extract_body(self, payload: dict) -> str:
        """Extract email body from Gmail message payload"""
        try:
            # Handle different payload structures
            if "parts" in payload:
                # Multipart message
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        body_data = part.get("body", {}).get("data")
                        if body_data:
                            return self._decode_base64(body_data)
                    elif part.get("mimeType") == "text/html":
                        body_data = part.get("body", {}).get("data")
                        if body_data:
                            html_content = self._decode_base64(body_data)
                            return self._html_to_text(html_content)
            else:
                # Single part message
                body_data = payload.get("body", {}).get("data")
                if body_data:
                    content = self._decode_base64(body_data)
                    if payload.get("mimeType") == "text/html":
                        return self._html_to_text(content)
                    return content
            
            return "No readable content found"
            
        except Exception:
            return "Error extracting email body"
    
    def _decode_base64(self, data: str) -> str:
        """Decode base64url encoded string"""
        try:
            # Gmail uses base64url encoding, replace characters
            data = data.replace("-", "+").replace("_", "/")
            while len(data) % 4:
                data += "="
            return base64.b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            return "Error decoding content"
    
    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML to plain text"""
        try:
            # Remove HTML tags and decode entities
            import re
            text = re.sub(r"<[^>]+>", "", html_content)
            text = html.unescape(text)
            return text.strip()
        except Exception:
            return html_content 