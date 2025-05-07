from collections.abc import Generator
from typing import Any, Dict, List
import json

import smartsheet
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class UpdateRowsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Update existing rows in a Smartsheet sheet.
        """
        # Get parameters
        sheet_id = tool_parameters.get("sheet_id")
        row_updates_str = tool_parameters.get("row_updates")
        
        # Validate parameters
        if not sheet_id:
            yield self.create_text_message("Sheet ID is required.")
            return
            
        if not row_updates_str:
            yield self.create_text_message("Row updates data is required.")
            return
            
        # Parse row_updates
        try:
            # Check if row_updates is a list or single object
            if row_updates_str.startswith('['):
                row_updates = json.loads(row_updates_str)
            else:
                # Single row update provided as object
                row_updates = [json.loads(row_updates_str)]
        except json.JSONDecodeError as e:
            yield self.create_text_message(f"Invalid row updates format. Please provide valid JSON: {str(e)}")
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
            
            # Get sheet information to get column map
            sheet = client.Sheets.get_sheet(sheet_id, include="columnIds")
            
            # Create column map: name -> id
            column_map = {col.title: col.id for col in sheet.columns}
            
            # Prepare rows for update
            updated_rows = []
            for update_item in row_updates:
                # Validate row_id is present
                if 'row_id' not in update_item:
                    yield self.create_text_message(f"Each row update must include a 'row_id' field. Skipping invalid row.")
                    continue
                
                row_id = update_item.pop('row_id')  # Extract row_id and remove from update data
                
                # Create cells for this row
                cells = []
                for col_name, value in update_item.items():
                    if col_name in column_map:
                        cells.append({
                            'columnId': column_map[col_name],
                            'value': value
                        })
                    else:
                        yield self.create_text_message(f"Warning: Column '{col_name}' does not exist in the sheet and will be ignored.")
                
                # Create row
                if cells:
                    updated_rows.append(smartsheet.models.Row(id=row_id, cells=cells))
            
            # Update rows
            if updated_rows:
                update_result = client.Sheets.update_rows(sheet_id, updated_rows)
                
                # Prepare response
                result = {
                    "sheet_id": sheet_id,
                    "sheet_name": sheet.name,
                    "rows_updated": len(update_result.data),
                    "success": True
                }
                
                # Send a text summary and the detailed JSON result
                summary = f"Updated {len(update_result.data)} row(s) in sheet '{sheet.name}'."
                yield self.create_text_message(summary)
                yield self.create_json_message(result)
            else:
                yield self.create_text_message("No valid rows to update. Please check your data.")
                
        except smartsheet.exceptions.SmartsheetException as e:
            error_message = f"Smartsheet API error: {str(e)}"
            yield self.create_text_message(error_message)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_text_message(error_message) 