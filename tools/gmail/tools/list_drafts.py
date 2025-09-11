import base64
import html
import urllib.parse
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListDraftsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # Get parameters
            limit = min(max(int(tool_parameters.get("limit", 10)), 1), 100)
            include_body = tool_parameters.get("include_body", False)
            search_query = tool_parameters.get("search_query", "").strip()
            
            # Get credentials from tool provider
            access_token = self.runtime.credentials.get("access_token")
            
            if not access_token:
                yield self.create_text_message("Error: No access token available. Please authorize the Gmail integration.")
                return
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            # Build search query for drafts
            final_query = "in:drafts"
            if search_query:
                final_query += f" {search_query}"
            
            # Search for draft messages
            search_params = {
                "q": final_query,
                "maxResults": limit
            }
            
            search_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?{urllib.parse.urlencode(search_params)}"
            
            yield self.create_text_message(f"Searching Gmail drafts for: '{final_query}' (max {limit} results)")
            
            search_response = requests.get(search_url, headers=headers, timeout=10)
            
            if search_response.status_code == 401:
                yield self.create_text_message("Error: Access token expired. Please re-authorize the Gmail integration.")
                return
            elif search_response.status_code != 200:
                yield self.create_text_message(f"Error: Gmail API returned status {search_response.status_code}")
                return
            
            search_data = search_response.json()
            messages = search_data.get("messages", [])
            
            if not messages:
                yield self.create_text_message("No draft emails found matching your criteria.")
                return
            
            yield self.create_text_message(f"Found {len(messages)} draft(s). Fetching details...")
            
            drafts = []
            for i, message in enumerate(messages):
                try:
                    message_id = message["id"]
                    
                    # Get message details - always use full format for complete draft data
                    message_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full"
                    
                    message_response = requests.get(message_url, headers=headers, timeout=10)
                    
                    if message_response.status_code != 200:
                        continue
                    
                    message_data = message_response.json()
                    draft_info = self._parse_draft(message_data, include_body)
                    drafts.append(draft_info)
                    
                    # Show progress for every 3 drafts
                    if (i + 1) % 3 == 0:
                        yield self.create_text_message(f"Processed {i + 1}/{len(messages)} drafts...")
                        
                except Exception as e:
                    continue  # Skip failed drafts
            
            if not drafts:
                yield self.create_text_message("Error: Could not retrieve draft details.")
                return
            
            # Return results
            yield self.create_json_message({
                "drafts": drafts,
                "total_found": len(drafts),
                "search_query": search_query if search_query else None,
                "query_used": final_query
            })
            
        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error listing drafts: {str(e)}")
    
    def _parse_draft(self, message_data: dict, include_body: bool = True) -> dict:
        """Parse Gmail draft message data into a clean format"""
        try:
            payload = message_data.get("payload", {})
            headers = payload.get("headers", [])
            
            # Extract headers
            draft_info = {
                "id": message_data.get("id"),
                "thread_id": message_data.get("threadId"),
                "labels": message_data.get("labelIds", []),
                "snippet": message_data.get("snippet", ""),
                "subject": "",
                "from": "",
                "to": "",
                "cc": "",
                "bcc": "",
                "date": "",
                "body": "",
                "has_attachments": False,
                "attachment_count": 0,
                "is_draft": True
            }
            
            # Parse headers
            for header in headers:
                name = header.get("name", "").lower()
                value = header.get("value", "")
                
                if name == "subject":
                    draft_info["subject"] = value
                elif name == "from":
                    draft_info["from"] = value
                elif name == "to":
                    draft_info["to"] = value
                elif name == "cc":
                    draft_info["cc"] = value
                elif name == "bcc":
                    draft_info["bcc"] = value
                elif name == "date":
                    draft_info["date"] = value
            
            # Check for attachments
            if "parts" in payload:
                draft_info["has_attachments"] = True
                draft_info["attachment_count"] = self._count_attachments(payload)
            
            # Extract body if requested
            if include_body:
                draft_info["body"] = self._extract_body(payload)
            
            return draft_info
            
        except Exception:
            return {
                "id": message_data.get("id", "unknown"),
                "error": "Failed to parse draft"
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