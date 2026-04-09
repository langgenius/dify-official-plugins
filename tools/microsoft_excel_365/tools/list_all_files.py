from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListAllFilesTool(Tool):
    """List all files in OneDrive to help find Excel workbooks"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List all files in OneDrive with optional filtering.
        """
        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message(
                "Access token is missing. Please authenticate first."
            )
            return

        # Extract parameters
        folder_path = tool_parameters.get("folder_path", "root")
        file_type_filter = tool_parameters.get("file_type", "all")
        max_results = tool_parameters.get("max_results", 50)
        site_id = tool_parameters.get("site_id")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            # Determine base drive URL (personal or SharePoint site drive)
            base_drive = (
                f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                if site_id
                else "https://graph.microsoft.com/v1.0/me/drive"
            )

            # Build the API URL based on folder path
            if folder_path == "root":
                url = f"{base_drive}/root/children"
            elif folder_path == "recent":
                url = f"{base_drive}/recent"
            elif folder_path.startswith("id:"):
                # If folder_path starts with "id:", treat it as a folder ID
                folder_id = folder_path[3:]
                url = f"{base_drive}/items/{folder_id}/children"
            else:
                # Try to navigate by path
                url = f"{base_drive}/root:/{folder_path}:/children"

            params = {
                "$top": str(max_results),
                "$select": "id,name,file,folder,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference",
                "$orderby": "name",
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                items = data.get("value", [])

                files = []
                folders = []
                excel_files = []

                for item in items:
                    item_info = {
                        "id": item["id"],
                        "name": item["name"],
                        "type": "folder" if item.get("folder") else "file",
                        "size": item.get("size", 0),
                        "created_date": item.get("createdDateTime", ""),
                        "modified_date": item.get("lastModifiedDateTime", ""),
                        "web_url": item.get("webUrl", ""),
                    }

                    if item.get("folder"):
                        item_info["child_count"] = item["folder"].get("childCount", 0)
                        folders.append(item_info)
                    else:
                        # It's a file
                        name_lower = item["name"].lower()
                        if name_lower.endswith((".xlsx", ".xls", ".xlsm", ".xlsb")):
                            item_info["file_type"] = "excel"
                            excel_files.append(item_info)
                        else:
                            item_info["file_type"] = "other"
                            files.append(item_info)

                # Apply file type filter
                filtered_items = []
                if file_type_filter == "excel":
                    filtered_items = excel_files
                elif file_type_filter == "folders":
                    filtered_items = folders
                elif file_type_filter == "all":
                    filtered_items = folders + excel_files + files
                else:
                    filtered_items = folders + excel_files + files

                if filtered_items:
                    result = {
                        "items": filtered_items,
                        "total_count": len(filtered_items),
                        "folder_count": len(folders),
                        "excel_count": len(excel_files),
                        "other_file_count": len(files),
                        "current_path": folder_path,
                    }

                    yield self.create_json_message(result)

                    # Create summary text
                    summary = (
                        f"Found {len(filtered_items)} item(s) in '{folder_path}':\n\n"
                    )

                    if folders:
                        summary += f"📁 Folders ({len(folders)}):\n"
                        for folder in folders[:5]:
                            summary += f"  - {folder['name']} ({folder['child_count']} items)\n"
                        if len(folders) > 5:
                            summary += f"  ... and {len(folders) - 5} more folders\n"
                        summary += "\n"

                    if excel_files:
                        summary += f"📊 Excel Files ({len(excel_files)}):\n"
                        for excel in excel_files[:10]:
                            size_mb = excel["size"] / (1024 * 1024)
                            summary += f"  - {excel['name']} ({size_mb:.2f} MB) [ID: {excel['id']}]\n"
                        if len(excel_files) > 10:
                            summary += (
                                f"  ... and {len(excel_files) - 10} more Excel files\n"
                            )
                        summary += "\n"

                    if files and file_type_filter != "excel":
                        summary += f"📄 Other Files ({len(files)}):\n"
                        for file in files[:5]:
                            summary += f"  - {file['name']}\n"
                        if len(files) > 5:
                            summary += f"  ... and {len(files) - 5} more files\n"

                    yield self.create_text_message(summary)
                else:
                    yield self.create_text_message(
                        f"No items found in '{folder_path}'."
                    )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"The path '{folder_path}' was not found."
                )
            else:
                yield self.create_text_message(
                    f"Failed to list files: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
