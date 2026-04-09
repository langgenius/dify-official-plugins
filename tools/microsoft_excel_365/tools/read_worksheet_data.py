from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ReadWorksheetDataTool(Tool):
    """Read data from an Excel worksheet"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Read data from a specified range in an Excel worksheet.
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
        range_address = tool_parameters.get("range", "A1:Z100")  # Default range
        site_id = tool_parameters.get("site_id")

        if not workbook_id:
            yield self.create_text_message("Workbook ID is required.")
            return
        if not worksheet_name:
            yield self.create_text_message("Worksheet name is required.")
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

            # Read data from the worksheet range
            url = f"{base_drive}/items/{workbook_id}/workbook/worksheets('{worksheet_name}')/range(address='{range_address}')"

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()

                # Extract the values
                values = data.get("values", [])
                row_count = data.get("rowCount", 0)
                column_count = data.get("columnCount", 0)
                address = data.get("address", "")

                # Format the data for output
                result = {
                    "workbook_id": workbook_id,
                    "worksheet": worksheet_name,
                    "range": address,
                    "row_count": row_count,
                    "column_count": column_count,
                    "values": values,
                }

                yield self.create_json_message(result)

                # Create summary text
                if values:
                    summary = f"Successfully read {row_count} rows × {column_count} columns from '{worksheet_name}' ({address})\n\n"

                    # Show first few rows as preview
                    preview_rows = min(5, len(values))
                    if preview_rows > 0:
                        summary += "Preview (first 5 rows):\n"
                        for i in range(preview_rows):
                            row_data = values[i]
                            summary += f"Row {i+1}: {row_data[:5] if len(row_data) > 5 else row_data}...\n"

                        if row_count > preview_rows:
                            summary += f"\n... and {row_count - preview_rows} more rows"

                    yield self.create_text_message(summary)
                else:
                    yield self.create_text_message(f"The range {address} is empty.")

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message(f"Workbook or worksheet not found.")
            else:
                yield self.create_text_message(
                    f"Failed to read worksheet data: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
