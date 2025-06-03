from collections.abc import Generator
from typing import Any
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListFilesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List files and folders in a NextCloud directory
        """
        # Get parameters
        path = tool_parameters.get("path", "/")
        include_size = tool_parameters.get("include_size", "true").lower() == "true"
        
        # Validate path
        if not path:
            path = "/"
        if not path.startswith("/"):
            path = "/" + path
            
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
            
            # Create client and list files
            client = Client(webdav_options)
            
            try:
                # List files in the specified path
                files = client.list(path)
                
                # Process the file list
                file_info_list = []
                for file_path in files:
                    # Skip the current directory entry
                    if file_path == path or file_path == path + "/":
                        continue
                    
                    # Get file information
                    try:
                        info = client.info(file_path)
                        file_info = {
                            "name": os.path.basename(file_path.rstrip('/')),
                            "path": file_path,
                            "type": "directory" if file_path.endswith('/') else "file"
                        }
                        
                        # Add size and modification date if available and requested
                        if include_size and 'size' in info:
                            file_info["size"] = info['size']
                        if 'modified' in info:
                            file_info["modified"] = info['modified']
                            
                        file_info_list.append(file_info)
                        
                    except Exception as e:
                        # If we can't get info for a specific file, just add basic info
                        file_info = {
                            "name": os.path.basename(file_path.rstrip('/')),
                            "path": file_path,
                            "type": "directory" if file_path.endswith('/') else "file"
                        }
                        file_info_list.append(file_info)
                
                # Create response
                if file_info_list:
                    summary = f"Found {len(file_info_list)} items in '{path}'"
                    yield self.create_text_message(summary)
                    yield self.create_json_message({
                        "path": path,
                        "items": file_info_list,
                        "total_count": len(file_info_list)
                    })
                else:
                    yield self.create_text_message(f"No files found in '{path}' or directory is empty.")
                    yield self.create_json_message({
                        "path": path,
                        "items": [],
                        "total_count": 0
                    })
                    
            except Exception as e:
                error_msg = str(e).lower()
                if 'not found' in error_msg or '404' in error_msg:
                    yield self.create_text_message(f"Directory '{path}' not found.")
                elif 'forbidden' in error_msg or '403' in error_msg:
                    yield self.create_text_message(f"Access denied to directory '{path}'.")
                else:
                    yield self.create_text_message(f"Error listing files in '{path}': {str(e)}")
                return
                
        except ImportError:
            yield self.create_text_message("webdavclient3 library is required but not installed.")
            return
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return 