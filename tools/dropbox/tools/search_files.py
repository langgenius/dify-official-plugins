from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils


class SearchFilesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search for files and folders in Dropbox
        """
        # Get parameters
        query = tool_parameters.get("query", "")
        max_results = tool_parameters.get("max_results", 10)
        
        # Validate parameters
        if not query:
            yield self.create_text_message("Search query is required.")
            return
            
        try:
            max_results = int(max_results)
        except ValueError:
            max_results = 10
            
        try:
            # Get access token from credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Dropbox access token is required.")
                return
                
            # Get Dropbox client
            try:
                dbx = DropboxUtils.get_client(access_token)
            except AuthError as e:
                yield self.create_text_message(f"Authentication failed: {str(e)}")
                return
            except Exception as e:
                yield self.create_text_message(f"Failed to connect to Dropbox: {str(e)}")
                return
                
            # Search files and folders
            try:
                items = DropboxUtils.search_files(dbx, query, max_results)
                
                if not items:
                    yield self.create_text_message(f"No results found for '{query}'")
                    return
                    
                # Create a response with search results
                result = {
                    "query": query,
                    "result_count": len(items),
                    "results": items
                }
                
                # Summarize the result
                summary = f"Found {len(items)} items matching '{query}'"
                yield self.create_text_message(summary)
                yield self.create_json_message(result)
                
            except ApiError as e:
                yield self.create_text_message(f"Error searching Dropbox: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return 