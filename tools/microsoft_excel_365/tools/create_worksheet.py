from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateWorksheetTool(Tool):
    """Create a new worksheet in an Excel workbook"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new worksheet in a specified Excel workbook.
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
        site_id = tool_parameters.get("site_id")

        if not workbook_id:
            yield self.create_text_message("Workbook ID is required.")
            return
        if not worksheet_name:
            yield self.create_text_message("Worksheet name is required.")
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

            # Create a new worksheet
            url = f"{base_drive}/items/{workbook_id}/workbook/worksheets"

            payload = {"name": worksheet_name}

            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 201:
                data = response.json()

                worksheet_info = {
                    "id": data["id"],
                    "name": data["name"],
                    "position": data.get("position", 0),
                    "visibility": data.get("visibility", "Visible"),
                }

                result = {
                    "workbook_id": workbook_id,
                    "worksheet": worksheet_info,
                    "status": "created",
                }

                yield self.create_json_message(result)
                yield self.create_text_message(
                    f"Successfully created new worksheet '{worksheet_name}' (ID: {worksheet_info['id']}) at position {worksheet_info['position'] + 1}."
                )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Workbook with ID '{workbook_id}' not found."
                )
            elif response.status_code == 400:
                error_msg = (
                    response.json().get("error", {}).get("message", "Bad request")
                )
                if "already exists" in error_msg.lower():
                    yield self.create_text_message(
                        f"A worksheet with the name '{worksheet_name}' already exists in this workbook."
                    )
                else:
                    yield self.create_text_message(f"Bad request: {error_msg}")
            else:
                yield self.create_text_message(
                    f"Failed to create worksheet: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
