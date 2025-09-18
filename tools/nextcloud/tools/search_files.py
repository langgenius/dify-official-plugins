import requests
import xml.etree.ElementTree as ET
from typing import Any, Generator
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class SearchFilesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Perform full-text search on Nextcloud files via OCS API and retrieve matching files regardless of hierarchy.
        """
        search_pattern = tool_parameters.get("search_pattern", "")
        search_path = tool_parameters.get("search_path", "/")
        max_results = int(tool_parameters.get("max_results", "50"))

        # Extract keywords (supports patterns like "*test*.*", "`test`", etc.)
        import re
        pattern = search_pattern.strip().strip("`'\"")  # Remove backticks and quotes
        pattern = pattern.strip("*")                    # Remove wildcard characters
        keyword = pattern.split(".")[0]                 # Remove file extension if present

        if not keyword:
            yield self.create_text_message("Search keyword is empty.")
            return

        # Nextcloud OCS API credentials
        webdav_hostname = self.runtime.credentials.get("webdav_hostname")
        username = self.runtime.credentials.get("username")
        app_password = self.runtime.credentials.get("app_password")
        if not all([webdav_hostname, username, app_password]):
            yield self.create_text_message("Nextcloud authentication information is not set.")
            return

        # OCS API endpoint
        if not webdav_hostname.endswith("/"):
            webdav_hostname += "/"
        if webdav_hostname.endswith("remote.php/webdav/"):
            webdav_hostname = webdav_hostname.replace("remote.php/webdav/", "")
        api_url = f"{webdav_hostname}ocs/v2.php/search/providers/files/search"

        headers = {
            "OCS-APIRequest": "true",
        }
        params = {
            "term": keyword
        }

        try:
            resp = requests.get(api_url, headers=headers, params=params, auth=(username, app_password), timeout=15)
            resp.raise_for_status()
        except Exception as e:
            yield self.create_text_message(f"Nextcloud OCS API request failed: {str(e)}")
            return

        # Parse the XML response
        try:
            root = ET.fromstring(resp.text)
        except Exception as e:
            yield self.create_text_message(f"Failed to parse OCS API response XML: {str(e)}")
            return

        # Extract file information from OCS response, applying search path filter and maximum result limit
        results = []
        found_count = 0

        # OCS hierarchical path matching
        def path_match(path: str, search_path: str) -> bool:
            # If search_path is "test1/**", match paths starting with /test1/ (completing slash)
            if not search_path.startswith("/"):
                search_path = "/" + search_path
            
            if search_path.endswith("/**"):
                base = search_path[:-3]
                return path.startswith(base)
            elif search_path.endswith("/*"):
                base = search_path[:-2]
                rel = path[len(base):].lstrip("/")
                return path.startswith(base) and ("/" not in rel)
            else:
                return path.startswith(search_path.rstrip("/"))

        # Retrieve 'entries' element from XML (expected path: ocs/data/entries)
        try:
            # Use XPath with namespace awareness
            entries = root.find(".//data/entries")
            if entries is None:
                yield self.create_text_message("OCS API response does not contain entries data.")
                return
        except Exception:
            yield self.create_text_message("Failed to parse OCS API response structure.")
            return

        # Process each element (file or folder)
        for element in entries.findall("element"):
            try:
                title_elem = element.find("title")
                path_elem = element.find("attributes/path")
                if title_elem is None or path_elem is None:
                    continue

                title = title_elem.text
                full_path = path_elem.text
                
                # Extract filename from title (should match the last path segment)
                if full_path:
                    # Get the actual filename from the path
                    name = full_path.split("/")[-1] if "/" in full_path else full_path
                else:
                    name = title

                # Check for match with search_path
                if path_match(full_path, search_path):
                    # Extract directory path
                    if "/" in full_path:
                        dir_path = full_path.rsplit("/", 1)[0]
                        if not dir_path:
                            dir_path = "/"
                    else:
                        dir_path = "/"
                    
                    results.append({
                        "name": name,
                        "path": dir_path,
                        "type": "file"
                    })
                    found_count += 1
                    if found_count >= max_results:
                        break
            except Exception:
                continue

        if results:
            found_texts = [f"Found 1 items matching '{r['name']}' in '{r['path']}'" for r in results]
            text = ", ".join(found_texts)
            json_output = {
                "max_results": max_results,
                "results": results,
                "search_path": search_path,
                "search_pattern": search_pattern,
                "total_found": found_count
            }
            yield self.create_text_message(text)
            yield self.create_json_message(json_output)
        else:
            json_output = {
                "max_results": max_results,
                "results": [],
                "search_path": search_path,
                "search_pattern": search_pattern,
                "total_found": 0
            }
            yield self.create_text_message("")
            yield self.create_json_message(json_output)
