from collections.abc import Generator
from typing import Any, Dict, List

import smartsheet
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class GetSheetInfoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Retrieve information about a Smartsheet sheet, including columns and sample data.
        """
        # Get sheet_id parameter
        sheet_id = tool_parameters.get("sheet_id")
        
        # Validate sheet_id
        if not sheet_id:
            yield self.create_text_message("Sheet ID is required.")
            return
            
        try:
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                yield self.create_text_message("Smartsheet API key is required.")
                return
                
            # Initialize Smartsheet client
            client = smartsheet.Smartsheet(api_key)
            client.errors_as_exceptions(True)
            
            # Get sheet information
            sheet = client.Sheets.get_sheet(sheet_id)
            
            # Extract column information
            columns = []
            column_map = {}
            for column in sheet.columns:
                column_info = {
                    "id": str(column.id),
                    "title": column.title,
                    "type": column.type,
                    "index": column.index,
                    "primary": column.primary
                }
                columns.append(column_info)
                column_map[column.title] = str(column.id)
            
            # Extract sample data (up to 5 rows)
            sample_data = []
            for idx, row in enumerate(sheet.rows[:5]):
                row_data = {}
                for cell in row.cells:
                    for column in sheet.columns:
                        if cell.column_id == column.id:
                            row_data[column.title] = cell.value
                            break
                row_data["row_id"] = str(row.id)
                sample_data.append(row_data)
            
            # Prepare response
            result = {
                "sheet_id": sheet_id,
                "sheet_name": sheet.name,
                "columns": columns,
                "column_map": column_map,
                "total_rows": sheet.total_row_count,
                "sample_data": sample_data
            }
            
            # Send a text summary and the detailed JSON result
            summary = f"Retrieved information for sheet '{sheet.name}' with {sheet.total_row_count} rows and {len(columns)} columns."
            yield self.create_text_message(summary)
            yield self.create_json_message(result)
                
        except smartsheet.exceptions.SmartsheetException as e:
            error_message = f"Smartsheet API error: {str(e)}"
            yield self.create_text_message(error_message)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_text_message(error_message) 