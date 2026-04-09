from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ClearWorksheetDataTool(Tool):
    """Clear data from an Excel worksheet range"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Clear data from a specified range in an Excel worksheet.
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
        worksheet_name = tool_parameters.get("worksheet_name")
        range_address = tool_parameters.get("range")
        site_id = tool_parameters.get("site_id")

        if not workbook_id:
            yield self.create_text_message("Workbook ID is required.")
            return
        if not worksheet_name:
            yield self.create_text_message("Worksheet name is required.")
            return
        if not range_address:
            yield self.create_text_message("Range is required.")
            return

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            # Determine base drive URL (personal or SharePoint site drive)
            base_drive = (
                f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
                if site_id
                else "https://graph.microsoft.com/v1.0/me/drive"
            )

            # Clear the worksheet range
            url = f"{base_drive}/items/{workbook_id}/workbook/worksheets('{worksheet_name}')/range(address='{range_address}')/clear"

            payload = {"applyTo": "Contents"}  # Clear only contents, not formatting

            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                result = {
                    "workbook_id": workbook_id,
                    "worksheet": worksheet_name,
                    "range_cleared": range_address,
                    "status": "success",
                }

                yield self.create_json_message(result)
                yield self.create_text_message(
                    f"Successfully cleared data from range '{range_address}' in worksheet '{worksheet_name}'."
                )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message(f"Workbook or worksheet not found.")
            elif response.status_code == 400:
                yield self.create_text_message(
                    f"Bad request. Please check the range format."
                )
            else:
                yield self.create_text_message(
                    f"Failed to clear worksheet data: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
