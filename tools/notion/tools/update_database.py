from collections.abc import Generator
from typing import Any, Dict, List
import json
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class UpdateDatabaseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        database_id = tool_parameters.get("database_id", "")
        title = tool_parameters.get("title", "")
        properties_json = tool_parameters.get("properties", "")
        
        # Validate parameters
        if not database_id:
            yield self.create_text_message("Database ID is required.")
            return
            
        if not title and not properties_json:
            yield self.create_text_message("At least one of title or properties must be provided.")
            return
        
        # Parse the properties JSON if provided
        properties = None
        if properties_json:
            try:
                properties = json.loads(properties_json)
                # Ensure properties is a dictionary
                if not isinstance(properties, dict):
                    yield self.create_text_message("Properties must be a JSON object with property names as keys.")
                    return
            except json.JSONDecodeError:
                yield self.create_text_message("Invalid JSON format for properties. Please provide a valid JSON object.")
                return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Format title for the database if provided
            title_content = None
            if title:
                title_content = client.format_rich_text(title)
            
            # Update the database
            try:
                database_data = client.update_database(database_id, title_content, properties)
                
                # Extract database ID and URL
                updated_id = database_data.get("id", "")
                database_url = client.format_page_url(updated_id)
                
                # Format the response
                result = {
                    "id": updated_id,
                    "url": database_url,
                    "updated": True
                }
                
                # Add details about what was updated
                updates = []
                if title:
                    result["title"] = title
                    updates.append("title")
                if properties:
                    result["properties_updated"] = True
                    updates.append("properties")
                
                update_text = ", ".join(updates)
                yield self.create_text_message(f"Database updated successfully. Updated: {update_text}")
                yield self.create_json_message(result)
                
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Database not found or you don't have access to it: {database_id}")
                elif e.response.status_code == 400:
                    yield self.create_text_message(f"Bad request: {str(e)}. Please check the properties format.")
                else:
                    yield self.create_text_message(f"Error updating database: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error updating Notion database: {str(e)}")
            return 