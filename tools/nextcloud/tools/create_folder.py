from collections.abc import Generator
from typing import Any
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateFolderTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new folder in NextCloud
        """
        # Get parameters
        folder_path = tool_parameters.get("folder_path", "")
        
        # Validate folder path
        if not folder_path:
            yield self.create_text_message("Folder path is required.")
            return
        if not folder_path.startswith("/"):
            folder_path = "/" + folder_path
            
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
                # Check if folder already exists
                if client.check(folder_path):
                    yield self.create_text_message(f"Folder '{folder_path}' already exists.")
                    return
                
                # Create the folder
                client.mkdir(folder_path)
                
                # Verify creation and get info
                if client.check(folder_path):
                    folder_info = {
                        "name": os.path.basename(folder_path.rstrip('/')),
                        "path": folder_path,
                        "type": "directory",
                        "created": True
                    }
                    
                    # Try to get additional info
                    try:
                        info = client.info(folder_path)
                        if 'modified' in info:
                            folder_info["created_date"] = info['modified']
                    except:
                        pass  # Info not critical
                    
                    summary = f"Successfully created folder '{os.path.basename(folder_path)}' at '{folder_path}'"
                    yield self.create_text_message(summary)
                    yield self.create_json_message(folder_info)
                else:
                    yield self.create_text_message(f"Failed to create folder '{folder_path}'. Folder creation was not confirmed.")
                    return
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'conflict' in error_msg or 'already exists' in error_msg:
                    yield self.create_text_message(f"Folder '{folder_path}' already exists.")
                elif 'not found' in error_msg or '404' in error_msg:
                    yield self.create_text_message(f"Parent directory does not exist. Cannot create '{folder_path}'.")
                elif 'forbidden' in error_msg or '403' in error_msg:
                    yield self.create_text_message(f"Access denied. Cannot create folder '{folder_path}'.")
                else:
                    yield self.create_text_message(f"Error creating folder '{folder_path}': {str(e)}")
                return
                
        except ImportError:
            yield self.create_text_message("webdavclient3 library is required but not installed.")
            return
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return 