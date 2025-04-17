from collections.abc import Generator
from typing import Any, Dict, List
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class RetrieveCommentsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        block_id = tool_parameters.get("block_id", "")
        page_size = int(tool_parameters.get("page_size", 100))
        
        # Validate parameters
        if not block_id:
            yield self.create_text_message("Block or Page ID is required.")
            return
            
        # Ensure page_size is within valid range
        if page_size < 1:
            page_size = 1
        if page_size > 100:
            page_size = 100
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Retrieve the comments
            try:
                comments_data = client.retrieve_comments(block_id, page_size=page_size)
                
                # Format the comments data
                formatted_comments = self._format_comments_data(client, comments_data)
                
                # Return results
                comment_count = len(formatted_comments.get("comments", []))
                
                if comment_count == 0:
                    yield self.create_text_message(f"No comments found for the specified block/page.")
                else:
                    yield self.create_text_message(f"Retrieved {comment_count} comment(s).")
                    
                yield self.create_json_message(formatted_comments)
                
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Block/Page not found or you don't have access to it: {block_id}")
                else:
                    yield self.create_text_message(f"Error retrieving comments: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error retrieving Notion comments: {str(e)}")
            return
    
    def _format_comments_data(self, client: NotionClient, comments_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format the comments data for the response."""
        result = {
            "comments": [],
            "has_more": comments_data.get("has_more", False),
            "next_cursor": comments_data.get("next_cursor")
        }
        
        comments = comments_data.get("results", [])
        
        for comment in comments:
            formatted_comment = {
                "id": comment.get("id", ""),
                "created_time": comment.get("created_time", ""),
                "last_edited_time": comment.get("last_edited_time", "")
            }
            
            # Extract comment text
            rich_text = comment.get("rich_text", [])
            formatted_comment["text"] = client.extract_plain_text(rich_text)
            
            # Extract user information if available
            created_by = comment.get("created_by", {})
            if created_by:
                user_info = {
                    "id": created_by.get("id", ""),
                    "object": created_by.get("object", "")
                }
                
                # Extract name if available
                if "name" in created_by:
                    user_info["name"] = created_by.get("name", "")
                    
                # Extract avatar URL if available
                if "avatar_url" in created_by:
                    user_info["avatar_url"] = created_by.get("avatar_url", "")
                    
                formatted_comment["created_by"] = user_info
            
            # Extract parent information
            parent = comment.get("parent", {})
            if parent:
                parent_type = parent.get("type", "")
                parent_id = ""
                
                if parent_type == "page_id":
                    parent_id = parent.get("page_id", "")
                elif parent_type == "block_id":
                    parent_id = parent.get("block_id", "")
                    
                formatted_comment["parent"] = {
                    "type": parent_type,
                    "id": parent_id
                }
            
            result["comments"].append(formatted_comment)
            
        return result 