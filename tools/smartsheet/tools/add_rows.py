from collections.abc import Generator
from typing import Any, Dict, List
import json

import smartsheet
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class AddRowsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Add one or more rows to a Smartsheet sheet.
        """
        # Get parameters
        sheet_id = tool_parameters.get("sheet_id")
        row_data_str = tool_parameters.get("row_data")
        to_top_str = tool_parameters.get("to_top", "true")
        
        # Validate parameters
        if not sheet_id:
            yield self.create_text_message("Sheet ID is required.")
            return
            
        if not row_data_str:
            yield self.create_text_message("Row data is required.")
            return
            
        # Parse row_data
        try:
            # Check if row_data is a list or single object
            if row_data_str.startswith('['):
                row_data = json.loads(row_data_str)
            else:
                # Single row provided as object
                row_data = [json.loads(row_data_str)]
        except json.JSONDecodeError as e:
            yield self.create_text_message(f"Invalid row data format. Please provide valid JSON: {str(e)}")
            return
        
        # Convert to_top string to boolean
        to_top = to_top_str.lower() == "true"
        
        try:
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                yield self.create_text_message("Smartsheet API key is required.")
                return
                
            # Initialize Smartsheet client
            client = smartsheet.Smartsheet(api_key)
            client.errors_as_exceptions(True)
            
            # Get sheet information to get column map
            sheet = client.Sheets.get_sheet(sheet_id, include="columnIds")
            
            # Create column map: name -> id
            column_map = {col.title: col.id for col in sheet.columns}
            
            # Prepare rows for addition
            new_rows = []
            for row_item in row_data:
                # Create cells for this row
                cells = []
                for col_name, value in row_item.items():
                    if col_name in column_map:
                        cells.append({
                            'columnId': column_map[col_name],
                            'value': value
                        })
                    else:
                        yield self.create_text_message(f"Warning: Column '{col_name}' does not exist in the sheet and will be ignored.")
                
                # Create row
                if cells:
                    new_rows.append(smartsheet.models.Row(to_top=to_top, cells=cells))
            
            # Add rows
            if new_rows:
                added_rows = client.Sheets.add_rows(sheet_id, new_rows)
                
                # Extract row IDs for response
                row_ids = [str(row.id) for row in added_rows.data]
                
                # Prepare response
                result = {
                    "sheet_id": sheet_id,
                    "sheet_name": sheet.name,
                    "rows_added": len(row_ids),
                    "row_ids": row_ids,
                    "success": True
                }
                
                # Send a text summary and the detailed JSON result
                summary = f"Added {len(row_ids)} row(s) to sheet '{sheet.name}'."
                yield self.create_text_message(summary)
                yield self.create_json_message(result)
            else:
                yield self.create_text_message("No valid rows to add. Please check your data.")
                
        except smartsheet.exceptions.SmartsheetException as e:
            error_message = f"Smartsheet API error: {str(e)}"
            yield self.create_text_message(error_message)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_text_message(error_message) 