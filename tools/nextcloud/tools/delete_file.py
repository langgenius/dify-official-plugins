from collections.abc import Generator
from typing import Any
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DeleteFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a file or folder from NextCloud
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")
        
        # Validate file path
        if not file_path:
            yield self.create_text_message("File or folder path is required.")
            return
        if not file_path.startswith("/"):
            file_path = "/" + file_path
            
        try:
            # Import webdavclient3 package (imported as webdav3.client)
            from webdav3.client import Client
            
            # Get credentials from runtime
            webdav_hostname = self.runtime.credentials.get("webdav_hostname")
            username = self.runtime.credentials.get("username")
            app_password = self.runtime.credentials.get("app_password")
            
            if not all([webdav_hostname, username, app_password]):
                yield self.create_text_message("NextCloud credentials are not properly configured.")
                return
            
            # Ensure hostname ends with /remote.php/webdav
            if not webdav_hostname.endswith('/'):
                webdav_hostname += '/'
            if not webdav_hostname.endswith('remote.php/webdav/'):
                webdav_hostname += 'remote.php/webdav/'
            
            # Create WebDAV client options
            webdav_options = {
                'webdav_hostname': webdav_hostname,
                'webdav_login': username,
                'webdav_password': app_password
            }
            
            # Create client
            client = Client(webdav_options)
            
            try:
                # Check if file/folder exists and get info before deletion
                if not client.check(file_path):
                    yield self.create_text_message(f"File or folder '{file_path}' not found.")
                    return
                
                # Get info about the item before deletion
                try:
                    file_info = client.info(file_path)
                    item_name = os.path.basename(file_path.rstrip('/'))
                    item_type = "folder" if file_path.endswith('/') or 'resourcetype' in file_info else "file"
                    item_size = file_info.get('size', 0)
                except:
                    # If we can't get info, proceed with basic info
                    item_name = os.path.basename(file_path.rstrip('/'))
                    item_type = "folder" if file_path.endswith('/') else "file"
                    item_size = 0
                
                # Delete the file/folder
                client.clean(file_path)
                
                # Verify deletion
                if not client.check(file_path):
                    deletion_info = {
                        "name": item_name,
                        "path": file_path,
                        "type": item_type,
                        "deleted": True,
                        "size": item_size
                    }
                    
                    summary = f"Successfully deleted {item_type} '{item_name}' from '{file_path}'"
                    yield self.create_text_message(summary)
                    yield self.create_json_message(deletion_info)
                else:
                    yield self.create_text_message(f"Failed to delete '{file_path}'. Item may still exist.")
                    return
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'not found' in error_msg or '404' in error_msg:
                    yield self.create_text_message(f"File or folder '{file_path}' not found.")
                elif 'forbidden' in error_msg or '403' in error_msg:
                    yield self.create_text_message(f"Access denied. Cannot delete '{file_path}'. Check permissions.")
                elif 'conflict' in error_msg:
                    yield self.create_text_message(f"Cannot delete '{file_path}'. Folder may not be empty.")
                else:
                    yield self.create_text_message(f"Error deleting '{file_path}': {str(e)}")
                return
                
        except ImportError:
            yield self.create_text_message("webdavclient3 library is required but not installed.")
            return
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return 