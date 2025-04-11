from collections.abc import Generator
from typing import Any, Dict, List
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

class RetrievePageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        page_id = tool_parameters.get("page_id", "")
        include_content = tool_parameters.get("include_content", True)
        
        # Validate parameters
        if not page_id:
            yield self.create_text_message("Page ID is required.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Retrieve the page
            try:
                page_data = client.retrieve_page(page_id)
                
                # Format the page data
                formatted_page = self._format_page_data(client, page_data)
                
                # Retrieve page content if requested
                if include_content:
                    try:
                        blocks_data = client.retrieve_block_children(page_id)
                        blocks = blocks_data.get("results", [])
                        formatted_page["content"] = self._format_blocks(blocks)
                    except requests.HTTPError as e:
                        # If we can't get the content, just return the page data
                        formatted_page["content_error"] = str(e)
                
                # Format URL
                formatted_page["url"] = client.format_page_url(page_id)
                
                # Return results
                title = formatted_page.get("title", "Untitled")
                yield self.create_text_message(f"Retrieved page: {title}")
                yield self.create_json_message(formatted_page)
                
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Page not found or you don't have access to it: {page_id}")
                else:
                    yield self.create_text_message(f"Error retrieving page: {e}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error retrieving Notion page: {str(e)}")
            return
    
    def _format_page_data(self, client: NotionClient, page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format the page data for the response."""
        result = {
            "id": page_data.get("id", ""),
            "created_time": page_data.get("created_time", ""),
            "last_edited_time": page_data.get("last_edited_time", ""),
            "archived": page_data.get("archived", False),
        }
        
        # Extract properties
        properties = page_data.get("properties", {})
        formatted_properties = {}
        
        title = "Untitled"
        for prop_name, prop_data in properties.items():
            prop_type = prop_data.get("type")
            
            # Extract value based on property type
            if prop_type == "title":
                title_content = prop_data.get("title", [])
                value = client.extract_plain_text(title_content)
                if value:
                    title = value  # Save title for the result
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
        
        result["title"] = title
        result["properties"] = formatted_properties
        return result
    
    def _format_blocks(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format block content for the response."""
        formatted_blocks = []
        
        for block in blocks:
            block_id = block.get("id", "")
            block_type = block.get("type", "")
            has_children = block.get("has_children", False)
            
            formatted_block = {
                "id": block_id,
                "type": block_type,
                "has_children": has_children
            }
            
            # Extract content based on block type
            if block_type == "paragraph":
                rich_text = block.get("paragraph", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type in ["heading_1", "heading_2", "heading_3"]:
                rich_text = block.get(block_type, {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type == "bulleted_list_item":
                rich_text = block.get("bulleted_list_item", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type == "numbered_list_item":
                rich_text = block.get("numbered_list_item", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type == "to_do":
                rich_text = block.get("to_do", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                checked = block.get("to_do", {}).get("checked", False)
                formatted_block["text"] = text
                formatted_block["checked"] = checked
            elif block_type == "code":
                code_block = block.get("code", {})
                rich_text = code_block.get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                language = code_block.get("language", "")
                formatted_block["text"] = text
                formatted_block["language"] = language
            elif block_type == "image":
                image_block = block.get("image", {})
                caption = image_block.get("caption", [])
                caption_text = "".join([rt.get("plain_text", "") for rt in caption])
                
                # Get image URL based on type
                image_type = image_block.get("type", "")
                if image_type == "external":
                    image_url = image_block.get("external", {}).get("url", "")
                elif image_type == "file":
                    image_url = image_block.get("file", {}).get("url", "")
                else:
                    image_url = ""
                
                formatted_block["caption"] = caption_text
                formatted_block["url"] = image_url
            else:
                # For unsupported block types, just include the type
                formatted_block["text"] = f"<{block_type} block>"
            
            formatted_blocks.append(formatted_block)
            
        return formatted_blocks 