from collections.abc import Generator
from typing import Any, Dict, List
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class CreateCommentTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        page_id = tool_parameters.get("page_id", "")
        content = tool_parameters.get("content", "")
        
        # Validate parameters
        if not page_id:
            yield self.create_text_message("Page ID is required.")
            return
            
        if not content:
            yield self.create_text_message("Comment content is required.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Create the comment
            try:
                # Prepare parent object
                parent = {"page_id": page_id}
                
                # Format rich text for comment
                rich_text = client.format_rich_text(content)
                
                # Create the comment
                comment_data = client.create_comment(parent, rich_text)
                
                # Format the response
                result = {
                    "id": comment_data.get("id", ""),
                    "created_time": comment_data.get("created_time", ""),
                    "content": content,
                    "page_id": page_id
                }
                
                # Extract user information if available
                created_by = comment_data.get("created_by", {})
                if created_by:
                    user_info = {
                        "id": created_by.get("id", ""),
                        "object": created_by.get("object", "")
                    }
                    
                    # Extract name if available
                    if "name" in created_by:
                        user_info["name"] = created_by.get("name", "")
                        
                    result["created_by"] = user_info
                
                yield self.create_text_message("Comment created successfully.")
                yield self.create_json_message(result)
                
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Page not found or you don't have access to it: {page_id}")
                else:
                    yield self.create_text_message(f"Error creating comment: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error creating Notion comment: {str(e)}")
            return 