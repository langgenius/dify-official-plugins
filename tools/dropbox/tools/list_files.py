from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils


class ListFilesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List files and folders in a specified Dropbox folder
        """
        # Get parameters
        folder_path = tool_parameters.get("folder_path", "")
        
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
                
            # List files and folders
            try:
                items = DropboxUtils.list_folder(dbx, folder_path)
                
                if not items:
                    yield self.create_text_message(f"No files or folders found in '{folder_path or 'root'}'")
                    return
                    
                # Create a response with folder contents
                result = {
                    "folder_path": folder_path or "root",
                    "item_count": len(items),
                    "items": items
                }
                
                # Summarize the result using an LLM if available
                summary = f"Found {len(items)} items in '{folder_path or 'root'}'"
                yield self.create_text_message(summary)
                yield self.create_json_message(result)
                
            except ApiError as e:
                yield self.create_text_message(f"Error listing folder contents: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return 