from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListWorksheetsTool(Tool):
    """List all worksheets in an Excel workbook"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List all worksheets in a specified Excel workbook.
        """
        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message(
                "Access token is missing. Please authenticate first."
            )
            return

        # Extract parameters
        workbook_id = tool_parameters.get("workbook_id")
        site_id = tool_parameters.get("site_id")
        if not workbook_id:
            yield self.create_text_message("Workbook ID is required.")
            return

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

            # Get worksheets from the workbook
            url = f"{base_drive}/items/{workbook_id}/workbook/worksheets"

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                worksheets = []

                for sheet in data.get("value", []):
                    worksheet_info = {
                        "id": sheet["id"],
                        "name": sheet["name"],
                        "position": sheet.get("position", 0),
                        "visibility": sheet.get("visibility", "Visible"),
                    }
                    worksheets.append(worksheet_info)

                if worksheets:
                    # Sort by position
                    worksheets.sort(key=lambda x: x["position"])

                    yield self.create_json_message(
                        {
                            "workbook_id": workbook_id,
                            "worksheets": worksheets,
                            "count": len(worksheets),
                        }
                    )

                    # Create summary text
                    summary = f"Found {len(worksheets)} worksheet(s) in the workbook:\n"
                    for ws in worksheets:
                        visibility = (
                            f" [{ws['visibility']}]"
                            if ws["visibility"] != "Visible"
                            else ""
                        )
                        summary += f"{ws['position'] + 1}. {ws['name']}{visibility} (ID: {ws['id']})\n"
                    yield self.create_text_message(summary)
                else:
                    yield self.create_text_message(
                        "No worksheets found in the workbook."
                    )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Workbook with ID '{workbook_id}' not found."
                )
            else:
                yield self.create_text_message(
                    f"Failed to list worksheets: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
