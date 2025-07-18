from collections.abc import Generator
from typing import Any
import base64
import tempfile
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DownloadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Download a file from NextCloud
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")
        include_content = tool_parameters.get("include_content", "false").lower() == "true"
        
        # Validate file path
        if not file_path:
            yield self.create_text_message("File path is required.")
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
                # Check if file exists and get info
                if not client.check(file_path):
                    yield self.create_text_message(f"File '{file_path}' not found.")
                    return
                
                # Get file information
                file_info = client.info(file_path)
                
                # Prepare response data
                response_data = {
                    "name": os.path.basename(file_path),
                    "path": file_path,
                    "size": file_info.get('size', 0),
                    "modified": file_info.get('modified', ''),
                    "content_type": file_info.get('content_type', 'application/octet-stream')
                }
                
                # Download content if requested
                if include_content:
                    try:
                        # Create temporary file for download
                        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                            temp_path = temp_file.name
                        
                        # Download file
                        client.download_file(file_path, temp_path)
                        
                        # Read file content
                        with open(temp_path, 'rb') as f:
                            file_content = f.read()
                        
                        # Clean up temp file
                        os.unlink(temp_path)
                        
                        # Try to decode as text if it looks like a text file
                        content_type = response_data.get('content_type', '').lower()
                        file_extension = os.path.splitext(file_path)[1].lower()
                        
                        text_types = ['text/', 'application/json', 'application/xml', 'application/yaml']
                        text_extensions = ['.txt', '.md', '.json', '.xml', '.yaml', '.yml', '.csv', '.log']
                        
                        is_text_file = (
                            any(content_type.startswith(t) for t in text_types) or
                            file_extension in text_extensions
                        )
                        
                        if is_text_file and len(file_content) < 10 * 1024 * 1024:  # Less than 10MB
                            try:
                                # Try to decode as UTF-8 text
                                text_content = file_content.decode('utf-8')
                                response_data["content_text"] = text_content
                                response_data["content_type"] = "text"
                            except UnicodeDecodeError:
                                # If text decoding fails, treat as binary
                                response_data["content_base64"] = base64.b64encode(file_content).decode('utf-8')
                                response_data["content_type"] = "binary"
                        else:
                            # Binary file or too large for text display
                            response_data["content_base64"] = base64.b64encode(file_content).decode('utf-8')
                            response_data["content_type"] = "binary"
                            
                        response_data["content_size"] = len(file_content)
                        
                    except Exception as e:
                        yield self.create_text_message(f"Error downloading file content: {str(e)}")
                        return
                
                # Create response
                if include_content:
                    if "content_text" in response_data:
                        summary = f"Downloaded text file '{os.path.basename(file_path)}' ({response_data['size']} bytes)"
                    else:
                        summary = f"Downloaded binary file '{os.path.basename(file_path)}' ({response_data['size']} bytes)"
                else:
                    summary = f"Retrieved metadata for '{os.path.basename(file_path)}' ({response_data['size']} bytes)"
                
                yield self.create_text_message(summary)
                yield self.create_json_message(response_data)
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'not found' in error_msg or '404' in error_msg:
                    yield self.create_text_message(f"File '{file_path}' not found.")
                elif 'forbidden' in error_msg or '403' in error_msg:
                    yield self.create_text_message(f"Access denied to file '{file_path}'.")
                else:
                    yield self.create_text_message(f"Error accessing file '{file_path}': {str(e)}")
                return
                
        except ImportError:
            yield self.create_text_message("webdavclient3 library is required but not installed.")
            return
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return 