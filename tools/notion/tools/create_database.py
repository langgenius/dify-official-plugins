from collections.abc import Generator
from typing import Any, Dict, List
import json
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class CreateDatabaseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        parent_page_id = tool_parameters.get("parent_page_id", "")
        title = tool_parameters.get("title", "")
        properties_json = tool_parameters.get("properties", "")
        
        # Validate parameters
        if not parent_page_id:
            yield self.create_text_message("Parent page ID is required.")
            return
            
        if not title:
            yield self.create_text_message("Database title is required.")
            return
            
        if not properties_json:
            yield self.create_text_message("Database properties are required.")
            return
        
        # Parse the properties JSON
        try:
            properties = json.loads(properties_json)
        except json.JSONDecodeError:
            yield self.create_text_message("Invalid JSON format for properties. Please provide a valid JSON object.")
            return
            
        # Ensure properties is a dictionary
        if not isinstance(properties, dict):
            yield self.create_text_message("Properties must be a JSON object with property names as keys.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Format the database creation payload
            parent = {"type": "page_id", "page_id": parent_page_id}
            
            # Format title for the database
            title_content = client.format_rich_text(title)
            
            # Create the database
            try:
                database_data = client.create_database(parent, title_content, properties)
                
                # Extract database ID and URL
                database_id = database_data.get("id", "")
                database_url = client.format_page_url(database_id)
                
                # Format the response
                result = {
                    "id": database_id,
                    "url": database_url,
                    "title": title,
                    "created": True
                }
                
                yield self.create_text_message(f"Database '{title}' created successfully.")
                yield self.create_json_message(result)
                
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Parent page not found or you don't have access to it: {parent_page_id}")
                elif e.response.status_code == 400:
                    yield self.create_text_message(f"Bad request: {str(e)}. Please check the properties format.")
                else:
                    yield self.create_text_message(f"Error creating database: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error creating Notion database: {str(e)}")
            return 