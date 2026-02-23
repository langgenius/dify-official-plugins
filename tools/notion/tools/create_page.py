from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class CreatePageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        title = tool_parameters.get("title", "")
        content = tool_parameters.get("content", "")
        parent_id = tool_parameters.get("parent_id", "")
        parent_type = tool_parameters.get("parent_type", "page")
        title_property_name = tool_parameters.get("title_property_name", "Name")
        
        # Validate parameters
        if not title:
            yield self.create_text_message("Page title is required.")
            return
            
        if not content:
            yield self.create_text_message("Page content is required.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Prepare parent object based on parent_type
            # Note: For 2025-09-03 API, database parents will be converted to data_source_id 
            # automatically by the NotionClient.create_page method
            parent_object = {}
            if parent_id:
                if parent_type.lower() == "database":
                    # The client will automatically convert this to data_source_id
                    parent_object = {
                        "database_id": parent_id
                    }
                elif parent_type.lower() == "data_source":
                    # Direct data_source_id (for 2025-09-03 API)
                    parent_object = {
                        "type": "data_source_id",
                        "data_source_id": parent_id
                    }
                else:  # Default to page
                    parent_object = {
                        "page_id": parent_id
                    }
            else:
                # If no parent_id is provided, create at workspace level
                parent_object = {
                    "workspace": True
                }
                
            # Prepare properties based on parent_type
            if parent_type.lower() in ["database", "data_source"]:
                # For database/data_source parents, use the title_property_name property as title
                # Default to "Name" if not specified
                properties = {
                    title_property_name: {
                        "title": [
                            {
                                "text": {
                                    "content": title
                                }
                            }
                        ]
                    }
                }
            else:
                # For page parents, use the standard title property
                properties = {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
                
            # Prepare content blocks
            children = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": content
                                }
                            }
                        ]
                    }
                }
            ]
            
            # Create the page
            try:
                data = client.create_page(
                    parent=parent_object,
                    properties=properties,
                    children=children
                )
                page_id = data.get("id", "")
                page_url = client.format_page_url(page_id)
                
                # Return success information
                summary = f"Successfully created page: {title}"
                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "id": page_id,
                    "title": title,
                    "url": page_url
                })
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Parent page or database not found: {parent_id}")
                else:
                    yield self.create_text_message(f"Error creating page: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error creating Notion page: {str(e)}")
            return