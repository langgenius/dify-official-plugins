from collections.abc import Generator
import base64
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils


class DownloadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Download a file from Dropbox
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")
        include_content = tool_parameters.get("include_content", False)
        
        # Validate parameters
        if not file_path:
            yield self.create_text_message("File path in Dropbox is required.")
            return
            
        # Make sure file path starts with /
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
                
            # Download the file
            try:
                result = DropboxUtils.download_file(dbx, file_path)
                
                # Create response
                response = {
                    "name": result["name"],
                    "path": result["path"],
                    "id": result["id"],
                    "size": result["size"],
                    "modified": result["modified"]
                }
                
                # Include content if requested
                if include_content:
                    # Encode binary content as base64
                    response["content_base64"] = base64.b64encode(result["content"]).decode('utf-8')
                    
                    # Try to decode as text if small enough
                    if result["size"] < 1024 * 1024:  # Less than 1MB
                        try:
                            text_content = result["content"].decode('utf-8')
                            response["content_text"] = text_content
                        except UnicodeDecodeError:
                            # Not a text file, just include base64
                            pass
                
                summary = f"File '{result['name']}' downloaded successfully"
                yield self.create_text_message(summary)
                yield self.create_json_message(response)
                
            except ApiError as e:
                yield self.create_text_message(f"Error downloading file: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return 