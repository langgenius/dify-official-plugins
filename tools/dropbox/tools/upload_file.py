from collections.abc import Generator
import io
import base64
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dropbox.exceptions import ApiError, AuthError

from dropbox_utils import DropboxUtils


class UploadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Upload a file to Dropbox
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")
        file_content = tool_parameters.get("file_content", "")
        file_content_base64 = tool_parameters.get("file_content_base64", "")
        overwrite = tool_parameters.get("overwrite", False)
        
        # Validate parameters
        if not file_path:
            yield self.create_text_message("File path in Dropbox is required.")
            return
            
        if not file_content and not file_content_base64:
            yield self.create_text_message("File content is required (either as text or base64).")
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
                
            # Prepare file content
            try:
                if file_content_base64:
                    # Decode base64 content
                    try:
                        content = base64.b64decode(file_content_base64)
                    except Exception:
                        yield self.create_text_message("Invalid base64 content provided.")
                        return
                else:
                    # Use regular text content
                    content = file_content.encode('utf-8')
                    
                # Upload the file
                result = DropboxUtils.upload_file(dbx, file_path, content, overwrite)
                
                # Create response
                summary = f"File uploaded successfully to {result['path']}"
                yield self.create_text_message(summary)
                yield self.create_json_message(result)
                
            except ApiError as e:
                yield self.create_text_message(f"Error uploading file: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return 