from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class QueryDatabaseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        database_id = tool_parameters.get("database_id", "")
        filter_property = tool_parameters.get("filter_property", "")
        filter_value = tool_parameters.get("filter_value", "")
        limit = int(tool_parameters.get("limit", 10))
        
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
            
            # Prepare filter if both property and value are provided
            filter_obj = None
            if filter_property and filter_value:
                filter_obj = client.create_simple_text_filter(filter_property, filter_value)
            
            # Query the database
            try:
                data = client.query_database(
                    database_id=database_id,
                    filter_obj=filter_obj,
                    page_size=limit
                )
                results = data.get("results", [])
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Database not found or you don't have access to it: {database_id}")
                else:
                    yield self.create_text_message(f"Error querying database: {e}")
                return
                
            if not results:
                filter_msg = f" with filter {filter_property}={filter_value}" if filter_property and filter_value else ""
                yield self.create_text_message(f"No results found in database{filter_msg}")
                return
                
            # Format results to extract and simplify property values
            formatted_results = []
            for result in results:
                # Get page ID and URL
                page_id = result.get("id")
                page_url = client.format_page_url(page_id)
                
                # Extract properties
                properties = result.get("properties", {})
                formatted_properties = {}
                
                for prop_name, prop_data in properties.items():
                    prop_type = prop_data.get("type")
                    
                    # Extract value based on property type
                    if prop_type == "title":
                        title_content = prop_data.get("title", [])
                        value = client.extract_plain_text(title_content)
                    elif prop_type == "rich_text":
                        text_content = prop_data.get("rich_text", [])
                        value = client.extract_plain_text(text_content)
                    elif prop_type == "number":
                        value = prop_data.get("number")
                    elif prop_type == "select":
                        select_data = prop_data.get("select", {})
                        value = select_data.get("name") if select_data else None
                    elif prop_type == "multi_select":
                        multi_select = prop_data.get("multi_select", [])
                        value = [item.get("name") for item in multi_select] if multi_select else []
                    elif prop_type == "date":
                        date_data = prop_data.get("date", {})
                        start = date_data.get("start") if date_data else None
                        end = date_data.get("end") if date_data else None
                        value = {"start": start, "end": end} if start else None
                    elif prop_type == "checkbox":
                        value = prop_data.get("checkbox")
                    elif prop_type == "url":
                        value = prop_data.get("url")
                    elif prop_type == "email":
                        value = prop_data.get("email")
                    elif prop_type == "phone_number":
                        value = prop_data.get("phone_number")
                    else:
                        # For other property types, just note the type
                        value = f"<{prop_type}>"
                    
                    formatted_properties[prop_name] = value
                
                # Add to formatted results
                formatted_results.append({
                    "id": page_id,
                    "url": page_url,
                    "properties": formatted_properties
                })
            
            # Return results
            filter_msg = f" with filter {filter_property}={filter_value}" if filter_property and filter_value else ""
            summary = f"Found {len(formatted_results)} results in database{filter_msg}"
            yield self.create_text_message(summary)
            yield self.create_json_message({"results": formatted_results})
            
        except Exception as e:
            yield self.create_text_message(f"Error querying Notion database: {str(e)}")
            return 