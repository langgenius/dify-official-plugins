from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SearchWorksheetDataTool(Tool):
    """Search for specific values in an Excel worksheet"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search for specific values in an Excel worksheet and return matching cells.
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
        search_value = tool_parameters.get("search_value")
        search_range = tool_parameters.get("range", "A1:Z1000")  # Default search range
        site_id = tool_parameters.get("site_id")

        if not workbook_id:
            yield self.create_text_message("Workbook ID is required.")
            return
        if not worksheet_name:
            yield self.create_text_message("Worksheet name is required.")
            return
        if not search_value:
            yield self.create_text_message("Search value is required.")
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

            # First, read the data from the specified range
            url = f"{base_drive}/items/{workbook_id}/workbook/worksheets('{worksheet_name}')/range(address='{search_range}')"

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                values = data.get("values", [])

                # Search for the value in the data
                matches = []
                for row_idx, row in enumerate(values):
                    for col_idx, cell_value in enumerate(row):
                        # Convert both to strings for comparison
                        if str(cell_value).lower() == str(search_value).lower():
                            # Convert column index to letter
                            col_letter = self._index_to_column_letter(col_idx)
                            row_number = row_idx + 1  # Excel rows are 1-indexed

                            match_info = {
                                "cell": f"{col_letter}{row_number}",
                                "value": cell_value,
                                "row": row_number,
                                "column": col_letter,
                            }
                            matches.append(match_info)

                if matches:
                    result = {
                        "workbook_id": workbook_id,
                        "worksheet": worksheet_name,
                        "search_value": search_value,
                        "matches": matches,
                        "match_count": len(matches),
                    }

                    yield self.create_json_message(result)

                    # Create summary text
                    summary = f"Found {len(matches)} match(es) for '{search_value}' in worksheet '{worksheet_name}':\n\n"
                    for match in matches[:10]:  # Show first 10 matches
                        summary += f"- Cell {match['cell']}: {match['value']}\n"

                    if len(matches) > 10:
                        summary += f"\n... and {len(matches) - 10} more matches"

                    yield self.create_text_message(summary)
                else:
                    yield self.create_text_message(
                        f"No matches found for '{search_value}' in the specified range."
                    )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Access token may be expired."
                )
            elif response.status_code == 404:
                yield self.create_text_message(f"Workbook or worksheet not found.")
            else:
                yield self.create_text_message(
                    f"Failed to search worksheet data: {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")

    def _index_to_column_letter(self, index: int) -> str:
        """Convert a column index (0-based) to Excel column letter (A, B, ..., Z, AA, AB, ...)"""
        letter = ""
        while index >= 0:
            letter = chr(index % 26 + ord("A")) + letter
            index = index // 26 - 1
        return letter
