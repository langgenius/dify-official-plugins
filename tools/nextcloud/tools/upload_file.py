from collections.abc import Generator
from typing import Any
import base64
import tempfile
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class UploadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Upload a file to NextCloud
        """
        # Get parameters
        file_path = tool_parameters.get("file_path", "")
        content = tool_parameters.get("content", "")
        content_type = tool_parameters.get("content_type", "text").lower()
        
        # Validate parameters
        if not file_path:
            yield self.create_text_message("File path is required.")
            return
        if not content:
            yield self.create_text_message("File content is required.")
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
                # Prepare file content
                if content_type == "base64":
                    try:
                        # Decode base64 content
                        file_data = base64.b64decode(content)
                    except Exception as e:
                        yield self.create_text_message(f"Invalid base64 content: {str(e)}")
                        return
                else:
                    # Text content
                    file_data = content.encode('utf-8')
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_file.write(file_data)
                    temp_path = temp_file.name
                
                try:
                    # Check if parent directory exists, create if needed
                    parent_dir = os.path.dirname(file_path)
                    if parent_dir and parent_dir != "/":
                        try:
                            if not client.check(parent_dir):
                                # Create parent directories
                                self._create_parent_dirs(client, parent_dir)
                        except Exception:
                            # Try to create anyway
                            pass
                    
                    # Upload the file
                    client.upload_file(file_path, temp_path)
                    
                    # Verify upload and get info
                    if client.check(file_path):
                        try:
                            file_info = client.info(file_path)
                            upload_info = {
                                "name": os.path.basename(file_path),
                                "path": file_path,
                                "size": file_info.get('size', len(file_data)),
                                "content_type": content_type,
                                "uploaded": True
                            }
                            if 'modified' in file_info:
                                upload_info["uploaded_date"] = file_info['modified']
                        except:
                            upload_info = {
                                "name": os.path.basename(file_path),
                                "path": file_path,
                                "size": len(file_data),
                                "content_type": content_type,
                                "uploaded": True
                            }
                        
                        summary = f"Successfully uploaded '{os.path.basename(file_path)}' ({len(file_data)} bytes) to '{file_path}'"
                        yield self.create_text_message(summary)
                        yield self.create_json_message(upload_info)
                    else:
                        yield self.create_text_message(f"Failed to upload file to '{file_path}'. Upload was not confirmed.")
                        return
                        
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'conflict' in error_msg:
                    yield self.create_text_message(f"File '{file_path}' already exists. Consider using a different name or delete the existing file first.")
                elif 'not found' in error_msg or '404' in error_msg:
                    yield self.create_text_message(f"Parent directory does not exist. Cannot upload to '{file_path}'.")
                elif 'forbidden' in error_msg or '403' in error_msg:
                    yield self.create_text_message(f"Access denied. Cannot upload to '{file_path}'. Check permissions.")
                elif 'insufficient storage' in error_msg or 'quota' in error_msg:
                    yield self.create_text_message(f"Insufficient storage space to upload '{file_path}'.")
                else:
                    yield self.create_text_message(f"Error uploading file to '{file_path}': {str(e)}")
                return
                
        except ImportError:
            yield self.create_text_message("webdavclient3 library is required but not installed.")
            return
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return
    
    def _create_parent_dirs(self, client, path):
        """
        Create parent directories recursively
        """
        path_parts = path.strip('/').split('/')
        current_path = ""
        
        for part in path_parts:
            current_path += "/" + part
            try:
                if not client.check(current_path):
                    client.mkdir(current_path)
            except Exception:
                # Continue if we can't create a directory
                pass 