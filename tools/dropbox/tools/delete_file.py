from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils


class DeleteFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a file or folder from Dropbox
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")
        
        # Validate parameters
        if not file_path:
            yield self.create_text_message("File or folder path in Dropbox is required.")
            return
            
        # Make sure path starts with /
        if not file_path.startswith("/"):
            file_path = "/" + file_path
            
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
                
            # Delete the file or folder
            try:
                result = DropboxUtils.delete_file(dbx, file_path)
                
                # Create response
                summary = f"'{result['name']}' deleted successfully"
                yield self.create_text_message(summary)
                yield self.create_json_message(result)
                
            except ApiError as e:
                if "path/not_found" in str(e):
                    yield self.create_text_message(f"File or folder not found at '{file_path}'")
                else:
                    yield self.create_text_message(f"Error deleting file/folder: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return 