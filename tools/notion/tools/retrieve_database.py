from collections.abc import Generator
from typing import Any, Dict, List
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class RetrieveDatabaseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        database_id = tool_parameters.get("database_id", "")
        
        # Validate parameters
        if not database_id:
            yield self.create_text_message("Database ID is required.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Retrieve the database
            try:
                database_data = client.retrieve_database(database_id)
                
                # Format the database data
                formatted_database = self._format_database_data(database_data)
                
                # Add URL
                formatted_database["url"] = client.format_page_url(database_id)
                
                # Return results
                database_title = formatted_database.get("title", "Untitled Database")
                yield self.create_text_message(f"Retrieved database: {database_title}")
                yield self.create_json_message(formatted_database)
                
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Database not found or you don't have access to it: {database_id}")
                else:
                    yield self.create_text_message(f"Error retrieving database: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error retrieving Notion database: {str(e)}")
            return
    
    def _format_database_data(self, database_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format the database data for the response."""
        result = {
            "id": database_data.get("id", ""),
            "created_time": database_data.get("created_time", ""),
            "last_edited_time": database_data.get("last_edited_time", ""),
            "title": "",
            "description": "",
            "properties": {}
        }
        
        # Extract title and description
        title = database_data.get("title", [])
        if title:
            result["title"] = "".join([text.get("plain_text", "") for text in title])
            
        description = database_data.get("description", [])
        if description:
            result["description"] = "".join([text.get("plain_text", "") for text in description])
            
        # Format properties schema
        properties = database_data.get("properties", {})
        formatted_properties = {}
        
        for prop_name, prop_data in properties.items():
            prop_type = prop_data.get("type", "")
            
            # Create a simplified representation of the property
            property_info = {
                "type": prop_type,
                "name": prop_name
            }
            
            # Add type-specific information
            if prop_type == "select":
                options = prop_data.get("select", {}).get("options", [])
                property_info["options"] = [option.get("name") for option in options]
            elif prop_type == "multi_select":
                options = prop_data.get("multi_select", {}).get("options", [])
                property_info["options"] = [option.get("name") for option in options]
            elif prop_type == "status":
                options = prop_data.get("status", {}).get("options", [])
                property_info["options"] = [option.get("name") for option in options]
            elif prop_type == "number":
                property_info["format"] = prop_data.get("number", {}).get("format")
            elif prop_type == "formula":
                property_info["expression"] = prop_data.get("formula", {}).get("expression")
            elif prop_type == "relation":
                property_info["database_id"] = prop_data.get("relation", {}).get("database_id")
            elif prop_type == "rollup":
                rollup = prop_data.get("rollup", {})
                property_info["rollup_property_name"] = rollup.get("rollup_property_name")
                property_info["relation_property_name"] = rollup.get("relation_property_name")
                property_info["function"] = rollup.get("function")
            
            formatted_properties[prop_name] = property_info
            
        result["properties"] = formatted_properties
        return result 