import base64
import html
import urllib.parse
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SearchMessagesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # Get parameters
            query = tool_parameters.get("query", "").strip()
            max_results = min(max(int(tool_parameters.get("max_results", 20)), 1), 100)
            include_body = tool_parameters.get("include_body", False)
            sort_by = tool_parameters.get("sort_by", "date").lower()
            
            if not query:
                yield self.create_text_message("Error: Search query is required.")
                return
            
            # Validate sort_by parameter
            valid_sort_options = ["date", "from", "subject"]
            if sort_by not in valid_sort_options:
                yield self.create_text_message(f"Error: Invalid sort option. Must be one of: {', '.join(valid_sort_options)}")
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
            
            # Build search parameters
            search_params = {
                "q": query,
                "maxResults": max_results
            }
            
            # Add sorting if specified
            if sort_by == "date":
                search_params["orderBy"] = "internalDate"
            elif sort_by == "from":
                search_params["orderBy"] = "from"
            elif sort_by == "subject":
                search_params["orderBy"] = "subject"
            
            search_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?{urllib.parse.urlencode(search_params)}"
            
            yield self.create_text_message(f"Searching Gmail for: '{query}' (max {max_results} results, sorted by {sort_by})")
            
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
                yield self.create_text_message("No messages found matching your search criteria.")
                return
            
            yield self.create_text_message(f"Found {len(messages)} message(s). Fetching details...")
            
            emails = []
            for i, message in enumerate(messages):
                try:
                    message_id = message["id"]
                    
                    # Get message details - always use full format to support search queries
                    message_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full"
                    
                    message_response = requests.get(message_url, headers=headers, timeout=10)
                    
                    if message_response.status_code != 200:
                        continue
                    
                    message_data = message_response.json()
                    email_info = self._parse_email(message_data, include_body)
                    emails.append(email_info)
                    
                    # Show progress for every 5 emails
                    if (i + 1) % 5 == 0:
                        yield self.create_text_message(f"Processed {i + 1}/{len(messages)} messages...")
                        
                except Exception as e:
                    continue  # Skip failed messages
            
            if not emails:
                yield self.create_text_message("Error: Could not retrieve message details.")
                return
            
            # Return results
            yield self.create_json_message({
                "messages": emails,
                "total_found": len(emails),
                "search_query": query,
                "sort_by": sort_by,
                "query_used": query
            })
            
        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error searching messages: {str(e)}")
    
    def _parse_email(self, message_data: dict, include_body: bool = True) -> dict:
        """Parse Gmail message data into a clean format"""
        try:
            payload = message_data.get("payload", {})
            headers = payload.get("headers", [])
            
            # Extract headers
            email_info = {
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
                "attachment_count": 0
            }
            
            # Parse headers
            for header in headers:
                name = header.get("name", "").lower()
                value = header.get("value", "")
                
                if name == "subject":
                    email_info["subject"] = value
                elif name == "from":
                    email_info["from"] = value
                elif name == "to":
                    email_info["to"] = value
                elif name == "cc":
                    email_info["cc"] = value
                elif name == "bcc":
                    email_info["bcc"] = value
                elif name == "date":
                    email_info["date"] = value
            
            # Check for attachments
            if "parts" in payload:
                email_info["has_attachments"] = True
                email_info["attachment_count"] = self._count_attachments(payload)
            
            # Extract body if requested
            if include_body:
                email_info["body"] = self._extract_body(payload)
            
            return email_info
            
        except Exception:
            return {
                "id": message_data.get("id", "unknown"),
                "error": "Failed to parse email"
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