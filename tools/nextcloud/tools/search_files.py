from collections.abc import Generator
from typing import Any
import os
import fnmatch

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SearchFilesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search for files and folders in NextCloud by name pattern
        """
        # Get parameters
        search_pattern = tool_parameters.get("search_pattern", "")
        search_path = tool_parameters.get("search_path", "/")
        max_results = int(tool_parameters.get("max_results", "50"))
        
        # Validate parameters
        if not search_pattern:
            yield self.create_text_message("Search pattern is required.")
            return
        if not search_path.startswith("/"):
            search_path = "/" + search_path
            
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
                # Check if search path exists
                if not client.check(search_path):
                    yield self.create_text_message(f"Search path '{search_path}' not found.")
                    return
                
                # Perform recursive search
                matching_files = []
                self._search_recursive(client, search_path, search_pattern, matching_files, max_results)
                
                if matching_files:
                    summary = f"Found {len(matching_files)} items matching '{search_pattern}' in '{search_path}'"
                    if len(matching_files) >= max_results:
                        summary += f" (limited to {max_results} results)"
                    
                    yield self.create_text_message(summary)
                    yield self.create_json_message({
                        "search_pattern": search_pattern,
                        "search_path": search_path,
                        "total_found": len(matching_files),
                        "max_results": max_results,
                        "results": matching_files
                    })
                else:
                    yield self.create_text_message(f"No files found matching '{search_pattern}' in '{search_path}'.")
                    yield self.create_json_message({
                        "search_pattern": search_pattern,
                        "search_path": search_path,
                        "total_found": 0,
                        "results": []
                    })
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'not found' in error_msg or '404' in error_msg:
                    yield self.create_text_message(f"Search path '{search_path}' not found.")
                elif 'forbidden' in error_msg or '403' in error_msg:
                    yield self.create_text_message(f"Access denied to search path '{search_path}'.")
                else:
                    yield self.create_text_message(f"Error searching in '{search_path}': {str(e)}")
                return
                
        except ImportError:
            yield self.create_text_message("webdavclient3 library is required but not installed.")
            return
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return
    
    def _search_recursive(self, client, path, pattern, results, max_results, depth=0):
        """
        Recursively search for files matching the pattern
        """
        # Prevent infinite recursion and limit depth
        if depth > 10 or len(results) >= max_results:
            return
        
        try:
            # List items in current directory
            items = client.list(path)
            
            for item_path in items:
                # Skip current directory entry
                if item_path == path or item_path == path + "/":
                    continue
                
                if len(results) >= max_results:
                    break
                
                # Get item name
                item_name = os.path.basename(item_path.rstrip('/'))
                
                # Check if name matches pattern
                if fnmatch.fnmatch(item_name.lower(), pattern.lower()):
                    try:
                        # Get item info
                        info = client.info(item_path)
                        item_info = {
                            "name": item_name,
                            "path": item_path,
                            "type": "directory" if item_path.endswith('/') else "file"
                        }
                        
                        # Add size and modification date if available
                        if 'size' in info:
                            item_info["size"] = info['size']
                        if 'modified' in info:
                            item_info["modified"] = info['modified']
                        
                        results.append(item_info)
                        
                    except Exception:
                        # If we can't get info, add basic info
                        item_info = {
                            "name": item_name,
                            "path": item_path,
                            "type": "directory" if item_path.endswith('/') else "file"
                        }
                        results.append(item_info)
                
                # If it's a directory, search recursively
                if item_path.endswith('/') and len(results) < max_results:
                    try:
                        self._search_recursive(client, item_path, pattern, results, max_results, depth + 1)
                    except Exception:
                        # Skip directories we can't access
                        continue
                        
        except Exception:
            # Skip directories we can't list
            pass 