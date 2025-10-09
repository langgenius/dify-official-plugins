import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class WriteWorksheetDataTool(Tool):
    """Write data to an Excel worksheet"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Write data to a specified range in an Excel worksheet.
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
        values = tool_parameters.get("values")
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
        if not values:
            yield self.create_text_message("Values are required.")
            return

        # Parse values if it's a string
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError:
                yield self.create_text_message(
                    "Invalid values format. Please provide a valid JSON array."
                )
                return

        # Ensure values is a 2D array
        if not isinstance(values, list):
            yield self.create_text_message("Values must be a 2D array.")
            return

        # If it's a 1D array, convert to 2D
        if values and not isinstance(values[0], list):
            values = [values]

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

            # Write data to the worksheet range
            url = f"{base_drive}/items/{workbook_id}/workbook/worksheets('{worksheet_name}')/range(address='{range_address}')"

            payload = {"values": values}

            response = requests.patch(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                data = response.json()

                row_count = data.get("rowCount", 0)
                column_count = data.get("columnCount", 0)
                address = data.get("address", "")

                result = {
                    "workbook_id": workbook_id,
                    "worksheet": worksheet_name,
                    "range": address,
                    "rows_written": row_count,
                    "columns_written": column_count,
                    "values": values,
                }

                yield self.create_json_message(result)

                # Create summary text
                summary = f"Successfully wrote {row_count} rows × {column_count} columns to '{worksheet_name}' ({address})\n\n"

                # Show what was written (preview)
                preview_rows = min(3, len(values))
                if preview_rows > 0:
                    summary += "Data written:\n"
                    for i in range(preview_rows):
                        row_data = values[i]
                        summary += f"Row {i+1}: {row_data[:5] if len(row_data) > 5 else row_data}\n"

                    if len(values) > preview_rows:
                        summary += f"... and {len(values) - preview_rows} more rows"

                yield self.create_text_message(summary)

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message(f"Workbook or worksheet not found.")
            elif response.status_code == 400:
                yield self.create_text_message(
                    f"Bad request. Please check the range and values format."
                )
            else:
                yield self.create_text_message(
                    f"Failed to write worksheet data: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
