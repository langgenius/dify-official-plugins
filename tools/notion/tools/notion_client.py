"""
Notion API Client for Dify plugins
This module provides a unified interface for interacting with the Notion API
"""

import requests
import time
from typing import Any, Dict, List, Optional, Union

class NotionClient:
    """
    A client for interacting with the Notion API.
    Abstracts the API calls and provides a unified interface for all Notion operations.
    """
    
    API_BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"  # Using a stable API version
    
    def __init__(self, integration_token: str):
        """
        Initialize the Notion client with an integration token.
        
        Args:
            integration_token: The Notion integration token for authentication
        """
        self.integration_token = integration_token
        self.headers = {
            "Authorization": f"Bearer {integration_token}",
            "Notion-Version": self.API_VERSION,
            "Content-Type": "application/json"
        }
        
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, 
                     json_data: Optional[Dict[str, Any]] = None, max_retries: int = 3) -> Dict[str, Any]:
        """
        Make an API request to Notion with retry logic for rate limits.
        
        Args:
            method: HTTP method (get, post, patch, etc.)
            endpoint: API endpoint (relative to base URL)
            params: URL parameters for GET requests
            json_data: JSON data for POST/PATCH requests
            max_retries: Maximum number of retries for rate limiting
            
        Returns:
            Response data as dictionary
        """
        url = f"{self.API_BASE_URL}{endpoint}"
        retries = 0
        
        while retries <= max_retries:
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json_data
                )
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    time.sleep(retry_after)
                    retries += 1
                    continue
                    
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.HTTPError as e:
                # Format error based on Notion's error response structure
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_json = e.response.json()
                        error_message = error_json.get('message', str(e))
                        error_code = error_json.get('code', 'unknown_error')
                        raise requests.exceptions.HTTPError(
                            f"Notion API Error: {error_code} - {error_message}", 
                            response=e.response
                        )
                    except ValueError:
                        # If not JSON response
                        pass
                raise
                
            except requests.exceptions.RequestException as e:
                if retries >= max_retries:
                    raise
                retries += 1
                time.sleep(1)
        
        # This should never happen, but just in case
        raise Exception("Maximum retries exceeded")
        
    def search(self, query: str, page_size: int = 10, start_cursor: Optional[str] = None, 
              filter_obj: Optional[Dict[str, Any]] = None, sort: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Search for pages and databases in a Notion workspace.
        
        Args:
            query: The search query string
            page_size: Maximum number of results to return (max 100)
            start_cursor: Cursor for pagination
            filter_obj: Filter object to restrict search to specific object types
            sort: Sort object to control the order of search results
            
        Returns:
            Dictionary containing search results
        """
        payload = {
            "query": query,
            "page_size": min(page_size, 100)  # Ensure page_size doesn't exceed API limit
        }
        
        if start_cursor:
            payload["start_cursor"] = start_cursor
            
        if filter_obj:
            payload["filter"] = filter_obj
            
        if sort:
            payload["sort"] = sort
            
        return self._make_request("post", "/search", json_data=payload)
    
    def query_database(self, database_id: str, filter_obj: Optional[Dict[str, Any]] = None, 
                       sorts: Optional[List[Dict[str, Any]]] = None, 
                       page_size: int = 10, start_cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Query a Notion database with optional filtering and sorting.
        
        Args:
            database_id: The ID of the database to query
            filter_obj: Optional filter object according to Notion API specs
            sorts: Optional sort specifications
            page_size: Maximum number of results to return (max 100)
            start_cursor: Cursor for pagination
            
        Returns:
            Dictionary containing database query results
        """
        # Clean database_id (remove dashes if present)
        database_id = database_id.replace("-", "")
        
        payload = {
            "page_size": min(page_size, 100)  # Ensure page_size doesn't exceed API limit
        }
        
        if filter_obj:
            payload["filter"] = filter_obj
            
        if sorts:
            payload["sorts"] = sorts
            
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        return self._make_request("post", f"/databases/{database_id}/query", json_data=payload)
    
    def create_page(self, parent: Dict[str, Any], properties: Dict[str, Any], 
                   children: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Create a new page in Notion with the specified parent, properties, and content.
        
        Args:
            parent: Parent specification (page_id, database_id, or workspace)
            properties: Page properties (including title)
            children: Optional list of block contents
            
        Returns:
            Dictionary containing the created page information
        """
        # Clean any IDs in the parent object
        if "page_id" in parent:
            parent["page_id"] = parent["page_id"].replace("-", "")
        elif "database_id" in parent:
            parent["database_id"] = parent["database_id"].replace("-", "")
        
        payload = {
            "parent": parent,
            "properties": properties
        }
        
        if children:
            payload["children"] = children
        
        return self._make_request("post", "/pages", json_data=payload)
    
    def retrieve_block_children(self, block_id: str, page_size: int = 100, start_cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve the children blocks of a block.
        
        Args:
            block_id: The ID of the block to retrieve children from
            page_size: Maximum number of results to return (max 100)
            start_cursor: Cursor for pagination
            
        Returns:
            Dictionary containing the block children
        """
        block_id = block_id.replace("-", "")
        
        params = {
            "page_size": min(page_size, 100)  # Ensure page_size doesn't exceed API limit
        }
        
        if start_cursor:
            params["start_cursor"] = start_cursor
            
        return self._make_request("get", f"/blocks/{block_id}/children", params=params)
    
    def append_block_children(self, block_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Append children blocks to a block.
        
        Args:
            block_id: The ID of the block to append children to
            children: List of block contents to append
            
        Returns:
            Dictionary containing the updated block information
        """
        block_id = block_id.replace("-", "")
        
        payload = {
            "children": children
        }
            
        return self._make_request("patch", f"/blocks/{block_id}/children", json_data=payload)
    
    def retrieve_page(self, page_id: str) -> Dict[str, Any]:
        """
        Retrieve a page by its ID.
        
        Args:
            page_id: The ID of the page to retrieve
            
        Returns:
            Dictionary containing the page information
        """
        page_id = page_id.replace("-", "")
        return self._make_request("get", f"/pages/{page_id}")
    
    def retrieve_database(self, database_id: str) -> Dict[str, Any]:
        """
        Retrieve a database by its ID.
        
        Args:
            database_id: The ID of the database to retrieve
            
        Returns:
            Dictionary containing the database information
        """
        database_id = database_id.replace("-", "")
        return self._make_request("get", f"/databases/{database_id}")
    
    def update_page(self, page_id: str, properties: Dict[str, Any], archived: bool = False) -> Dict[str, Any]:
        """
        Update a page's properties.
        
        Args:
            page_id: The ID of the page to update
            properties: The properties to update
            archived: Whether to archive the page
            
        Returns:
            Dictionary containing the updated page information
        """
        page_id = page_id.replace("-", "")
        
        payload = {
            "properties": properties
        }
        
        if archived:
            payload["archived"] = True
        
        return self._make_request("patch", f"/pages/{page_id}", json_data=payload)
    
    def update_block(self, block_id: str, block_data: Dict[str, Any], archived: bool = False) -> Dict[str, Any]:
        """
        Update a block.
        
        Args:
            block_id: The ID of the block to update
            block_data: The data to update the block with
            archived: Whether to archive the block
            
        Returns:
            Dictionary containing the updated block information
        """
        block_id = block_id.replace("-", "")
        
        payload = block_data
        
        if archived:
            payload["archived"] = True
            
        return self._make_request("patch", f"/blocks/{block_id}", json_data=payload)
    
    def create_property_filter(self, property_name: str, property_type: str, 
                               condition: str, value: Any) -> Dict[str, Any]:
        """
        Create a property filter for database queries.
        
        Args:
            property_name: Name of the property to filter on
            property_type: Type of the property (text, number, checkbox, etc.)
            condition: Filter condition (equals, contains, greater_than, etc.)
            value: Value to filter by
            
        Returns:
            Filter object for use with query_database
        """
        return {
            "property": property_name,
            property_type: {
                condition: value
            }
        }
    
    def create_simple_text_filter(self, property_name: str, filter_value: str, condition: str = "equals") -> Dict[str, Any]:
        """
        Create a simple text filter for database queries.
        
        Args:
            property_name: Name of the property to filter on
            filter_value: Value to filter by
            condition: Filter condition (equals, contains, starts_with, ends_with)
            
        Returns:
            Filter object for use with query_database
        """
        return self.create_property_filter(property_name, "rich_text", condition, filter_value)
    
    def format_page_url(self, page_id: str) -> str:
        """
        Format a page ID into a Notion URL.
        
        Args:
            page_id: The page ID
            
        Returns:
            Formatted Notion URL for the page
        """
        # Make sure the page_id is properly formatted (with hyphens)
        clean_id = page_id.replace("-", "")
        formatted_id = f"{clean_id[0:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"
        return f"https://notion.so/{formatted_id}"
    
    def extract_plain_text(self, rich_text_array: List[Dict[str, Any]]) -> str:
        """
        Extract plain text from a rich text array.
        
        Args:
            rich_text_array: Array of rich text objects
            
        Returns:
            Plain text string
        """
        if not rich_text_array:
            return ""
        
        return "".join([text.get("plain_text", "") for text in rich_text_array])
        
    def create_rich_text(self, content: str, annotations: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Create a rich text array with the specified content and optional annotations.
        
        Args:
            content: The text content
            annotations: Optional text annotations (bold, italic, etc.)
            
        Returns:
            Rich text array for use with Notion API
        """
        rich_text = {
            "type": "text",
            "text": {
                "content": content
            }
        }
        
        if annotations:
            rich_text["annotations"] = annotations
            
        return [rich_text]
    
    def create_paragraph_block(self, text_content: str) -> Dict[str, Any]:
        """
        Create a paragraph block with the specified text content.
        
        Args:
            text_content: The text content of the paragraph
            
        Returns:
            Paragraph block for use with Notion API
        """
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": self.create_rich_text(text_content)
            }
        }
        
    def create_heading_block(self, text_content: str, level: int = 1) -> Dict[str, Any]:
        """
        Create a heading block with the specified text content and level.
        
        Args:
            text_content: The text content of the heading
            level: Heading level (1, 2, or 3)
            
        Returns:
            Heading block for use with Notion API
        """
        if level not in [1, 2, 3]:
            raise ValueError("Heading level must be 1, 2, or 3")
            
        heading_type = f"heading_{level}"
        
        return {
            "object": "block",
            "type": heading_type,
            heading_type: {
                "rich_text": self.create_rich_text(text_content)
            }
        }
        
    def create_bulleted_list_block(self, text_content: str) -> Dict[str, Any]:
        """
        Create a bulleted list item block with the specified text content.
        
        Args:
            text_content: The text content of the list item
            
        Returns:
            Bulleted list item block for use with Notion API
        """
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": self.create_rich_text(text_content)
            }
        }
        
    def create_numbered_list_block(self, text_content: str) -> Dict[str, Any]:
        """
        Create a numbered list item block with the specified text content.
        
        Args:
            text_content: The text content of the list item
            
        Returns:
            Numbered list item block for use with Notion API
        """
        return {
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {
                "rich_text": self.create_rich_text(text_content)
            }
        }
        
    def create_database(self, parent: Dict[str, Any], title: List[Dict[str, Any]], 
                         properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new database in a parent page.
        
        Args:
            parent: The parent object with page_id
            title: The title for the database as rich text array
            properties: The properties schema for the database
            
        Returns:
            The created database object
        """
        endpoint = "/databases"
        payload = {
            "parent": parent,
            "title": title,
            "properties": properties
        }
        
        return self._make_request("POST", endpoint, json_data=payload)
    
    def update_database(self, database_id: str, title: Optional[List[Dict[str, Any]]] = None,
                         properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Update an existing database.
        
        Args:
            database_id: The ID of the database to update
            title: Optional new title for the database
            properties: Optional properties to update
            
        Returns:
            The updated database object
        """
        endpoint = f"/databases/{database_id}"
        payload = {}
        
        if title:
            payload["title"] = title
            
        if properties:
            payload["properties"] = properties
            
        return self._make_request("PATCH", endpoint, json_data=payload)
    
    def retrieve_comments(self, block_id: str, page_size: int = 100, 
                           start_cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve comments from a block or page.
        
        Args:
            block_id: The ID of the block or page
            page_size: Maximum number of comments to retrieve
            start_cursor: Pagination cursor
            
        Returns:
            Comments data including results array
        """
        endpoint = f"/comments"
        params = {
            "block_id": block_id,
            "page_size": page_size
        }
        
        if start_cursor:
            params["start_cursor"] = start_cursor
            
        return self._make_request("GET", endpoint, params=params)
    
    def create_comment(self, parent: Dict[str, Any], rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a new comment on a page.
        
        Args:
            parent: The parent object with page_id
            rich_text: The rich text content for the comment
            
        Returns:
            The created comment object
        """
        endpoint = "/comments"
        payload = {
            "parent": parent,
            "rich_text": rich_text
        }
        
        return self._make_request("POST", endpoint, json_data=payload)
    
    def format_rich_text(self, content: str) -> List[Dict[str, Any]]:
        """
        Format plain text into rich text array for Notion API.
        Wrapper around create_rich_text for simplified usage.
        
        Args:
            content: Plain text content
            
        Returns:
            Rich text array for Notion API
        """
        return self.create_rich_text(content) 