from collections.abc import Generator
from typing import Any, Dict, List
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class UpdatePageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        page_id = tool_parameters.get("page_id", "")
        title = tool_parameters.get("title", "")
        content = tool_parameters.get("content", "")
        archive = tool_parameters.get("archive", False)
        
        # Validate parameters
        if not page_id:
            yield self.create_text_message("Page ID is required.")
            return
            
        if not title and not content and not archive:
            yield self.create_text_message("At least one of title, content, or archive must be provided.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # First retrieve the page to check if it exists and get its current properties
            try:
                # Get the page
                page_data = client.retrieve_page(page_id)
                
                # Now perform updates based on provided parameters
                
                # Update title if provided
                if title:
                    try:
                        # First get the title property name
                        properties = page_data.get("properties", {})
                        title_prop_name = None
                        
                        # Find the title property
                        for prop_name, prop_data in properties.items():
                            if prop_data.get("type") == "title":
                                title_prop_name = prop_name
                                break
                        
                        if title_prop_name:
                            # Update the title
                            updated_properties = {
                                title_prop_name: {
                                    "title": [
                                        {
                                            "text": {
                                                "content": title
                                            }
                                        }
                                    ]
                                }
                            }
                            
                            # Update the page properties
                            client.update_page(page_id, updated_properties, archived=archive)
                        else:
                            yield self.create_text_message("Could not find title property in page.")
                            return
                            
                    except requests.HTTPError as e:
                        yield self.create_text_message(f"Error updating page title: {e}")
                        return
                # If only archiving, do that
                elif archive:
                    try:
                        client.update_page(page_id, {}, archived=True)
                    except requests.HTTPError as e:
                        yield self.create_text_message(f"Error archiving page: {e}")
                        return
                
                # Add new content if provided
                if content:
                    try:
                        # Create paragraph block with content
                        paragraph_block = client.create_paragraph_block(content)
                        
                        # Append the block to the page
                        client.append_block_children(page_id, [paragraph_block])
                        
                    except requests.HTTPError as e:
                        yield self.create_text_message(f"Error adding content to page: {e}")
                        return
                
                # Return success response
                page_url = client.format_page_url(page_id)
                
                # Create response message
                actions = []
                if title:
                    actions.append(f"updated title to '{title}'")
                if content:
                    actions.append("added new content")
                if archive:
                    actions.append("archived the page")
                
                action_text = ", ".join(actions)
                summary = f"Successfully {action_text}"
                
                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "id": page_id,
                    "url": page_url,
                    "updated": True,
                    "actions": actions
                })
                
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Page not found or you don't have access to it: {page_id}")
                else:
                    yield self.create_text_message(f"Error updating page: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error updating Notion page: {str(e)}")
            return 