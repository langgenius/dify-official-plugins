from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class SearchNotionTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        query = tool_parameters.get("query", "")
        limit = int(tool_parameters.get("limit", 10))
        
        # Validate parameters
        if not query:
            yield self.create_text_message("Search query is required.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Perform the search
            try:
                data = client.search(query=query, page_size=limit)
                results = data.get("results", [])
            except requests.HTTPError as e:
                yield self.create_text_message(f"Error searching Notion: {e}")
                return
                
            if not results:
                yield self.create_text_message(f"No results found for query: '{query}'")
                return
                
            # Format results
            formatted_results = []
            for result in results:
                object_type = result.get("object")
                result_id = result.get("id")
                
                # Get title based on object type
                title = "Untitled"
                if object_type == "page":
                    title_content = result.get("properties", {}).get("title", {}).get("title", [])
                    if title_content:
                        title = client.extract_plain_text(title_content)
                elif object_type == "database":
                    title_content = result.get("title", [])
                    if title_content:
                        title = client.extract_plain_text(title_content)
                
                # Create URL
                url = client.format_page_url(result_id)
                
                # Add to formatted results
                formatted_results.append({
                    "id": result_id,
                    "title": title,
                    "type": object_type,
                    "url": url
                })
            
            # Return results
            summary = f"Found {len(formatted_results)} results for '{query}'"
            yield self.create_text_message(summary)
            yield self.create_json_message({"results": formatted_results})
            
        except Exception as e:
            yield self.create_text_message(f"Error searching Notion: {str(e)}")
            return 