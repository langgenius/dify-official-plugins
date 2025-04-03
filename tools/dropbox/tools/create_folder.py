from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils


class CreateFolderTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a folder in Dropbox
        """
        # Get parameters
        folder_path = tool_parameters.get("folder_path", "")
        
        # Validate parameters
        if not folder_path:
            yield self.create_text_message("Folder path in Dropbox is required.")
            return
            
        # Make sure folder path starts with /
        if not folder_path.startswith("/"):
            folder_path = "/" + folder_path
            
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
                
            # Create the folder
            try:
                result = DropboxUtils.create_folder(dbx, folder_path)
                
                # Create response
                summary = f"Folder '{result['name']}' created successfully at '{result['path']}'"
                yield self.create_text_message(summary)
                yield self.create_json_message(result)
                
            except ApiError as e:
                if "path/conflict" in str(e):
                    yield self.create_text_message(f"A folder already exists at '{folder_path}'")
                else:
                    yield self.create_text_message(f"Error creating folder: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return 