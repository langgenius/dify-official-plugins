from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListWorkbooksTool(Tool):
    """List all Excel workbooks accessible to the user"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List all Excel workbooks in the user's OneDrive or SharePoint.
        """
        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message(
                "Access token is missing. Please authenticate first."
            )
            return

        # Extract parameters
        folder_id = tool_parameters.get("folder_id", "")
        search_query = tool_parameters.get("search_query", "")
        max_results = tool_parameters.get("max_results", 20)
        site_id = tool_parameters.get("site_id")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            workbooks = []

            # Determine base drive URL (personal or SharePoint site drive)
            base_drive = (
                f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                if site_id
                else "https://graph.microsoft.com/v1.0/me/drive"
            )

            if search_query:
                # Use search endpoint for searching
                # Use root/search for broader compatibility across drive types
                url = f"{base_drive}/root/search(q='{search_query}')"
                params = {"$top": str(max_results)}
            elif folder_id:
                # List files in specific folder
                url = f"{base_drive}/items/{folder_id}/children"
                params = {
                    "$top": str(max_results),
                    "$select": "id,name,file,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference",
                }
            else:
                # Use a more targeted approach - get recent files first
                url = f"{base_drive}/recent"
                params = {"$top": str(max_results)}

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                items = data.get("value", [])

                # Filter for Excel files
                for item in items:
                    if item.get("file") and item.get("name", "").lower().endswith(
                        (".xlsx", ".xls", ".xlsm", ".xlsb")
                    ):
                        workbook_info = {
                            "id": item["id"],
                            "name": item["name"],
                            "size": item.get("size", 0),
                            "created_date": item.get("createdDateTime", ""),
                            "modified_date": item.get("lastModifiedDateTime", ""),
                            "web_url": item.get("webUrl", ""),
                            "path": item.get("parentReference", {}).get("path", ""),
                        }
                        workbooks.append(workbook_info)

                # If no workbooks found in recent, try root folder
                if not workbooks and not search_query and not folder_id:
                    url = f"{base_drive}/root/children"
                    params = {
                        "$top": str(max_results),
                        "$select": "id,name,file,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference",
                    }

                    response = requests.get(
                        url, headers=headers, params=params, timeout=30
                    )
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get("value", [])

                        for item in items:
                            if item.get("file") and item.get(
                                "name", ""
                            ).lower().endswith((".xlsx", ".xls", ".xlsm", ".xlsb")):
                                workbook_info = {
                                    "id": item["id"],
                                    "name": item["name"],
                                    "size": item.get("size", 0),
                                    "created_date": item.get("createdDateTime", ""),
                                    "modified_date": item.get(
                                        "lastModifiedDateTime", ""
                                    ),
                                    "web_url": item.get("webUrl", ""),
                                    "path": item.get("parentReference", {}).get(
                                        "path", ""
                                    ),
                                }
                                workbooks.append(workbook_info)

                if workbooks:
                    yield self.create_json_message(
                        {"workbooks": workbooks, "count": len(workbooks)}
                    )

                    # Create summary text
                    summary = f"Found {len(workbooks)} Excel workbook(s):\n"
                    for wb in workbooks:
                        summary += f"- {wb['name']} (ID: {wb['id']})\n"
                    yield self.create_text_message(summary)
                else:
                    # Provide helpful message
                    if search_query:
                        yield self.create_text_message(
                            f"No Excel workbooks found matching '{search_query}'."
                        )
                    elif folder_id:
                        yield self.create_text_message(
                            f"No Excel workbooks found in the specified folder."
                        )
                    else:
                        yield self.create_text_message(
                            "No Excel workbooks found. Try uploading an Excel file to OneDrive first."
                        )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message("The specified folder was not found.")
            else:
                yield self.create_text_message(
                    f"Failed to list workbooks: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
