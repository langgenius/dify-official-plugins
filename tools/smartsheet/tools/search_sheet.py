from collections.abc import Generator
from typing import Any, Dict, List
import re

import smartsheet
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class SearchSheetTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search for data within a Smartsheet sheet.
        """
        # Get parameters
        sheet_id = tool_parameters.get("sheet_id")
        search_term = tool_parameters.get("search_term")
        max_results_str = tool_parameters.get("max_results", "10")
        
        # Validate parameters
        if not sheet_id:
            yield self.create_text_message("Sheet ID is required.")
            return
            
        if not search_term:
            yield self.create_text_message("Search term is required.")
            return
            
        # Convert max_results to integer
        try:
            max_results = int(max_results_str)
            if max_results <= 0:
                max_results = 10
                yield self.create_text_message("Warning: max_results must be positive. Using default value of 10.")
        except ValueError:
            max_results = 10
            yield self.create_text_message("Warning: Invalid max_results value. Using default value of 10.")
        
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
            
            # Create case-insensitive regex pattern for search
            pattern = re.compile(search_term, re.IGNORECASE)
            
            # Search through sheet data
            matching_rows = []
            row_count = 0
            
            for row in sheet.rows:
                # Check if we've reached the max number of results
                if row_count >= max_results:
                    break
                
                # Parse row data
                row_data = {}
                match_found = False
                
                for cell in row.cells:
                    # Find the column name for this cell
                    column_name = None
                    for column in sheet.columns:
                        if cell.column_id == column.id:
                            column_name = column.title
                            break
                    
                    # Skip if we couldn't find the column name
                    if not column_name or cell.value is None:
                        continue
                    
                    # Store the cell value
                    cell_value = str(cell.value)
                    row_data[column_name] = cell_value
                    
                    # Check for match in this cell
                    if pattern.search(cell_value):
                        match_found = True
                
                # If we found a match in this row, add it to results
                if match_found:
                    row_data["row_id"] = str(row.id)
                    matching_rows.append(row_data)
                    row_count += 1
            
            # Prepare response
            result = {
                "sheet_id": sheet_id,
                "sheet_name": sheet.name,
                "search_term": search_term,
                "matches_found": len(matching_rows),
                "results": matching_rows
            }
            
            # Send a text summary and the detailed JSON result
            if matching_rows:
                summary = f"Found {len(matching_rows)} row(s) containing '{search_term}' in sheet '{sheet.name}'."
            else:
                summary = f"No rows found containing '{search_term}' in sheet '{sheet.name}'."
                
            yield self.create_text_message(summary)
            yield self.create_json_message(result)
                
        except smartsheet.exceptions.SmartsheetException as e:
            error_message = f"Smartsheet API error: {str(e)}"
            yield self.create_text_message(error_message)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield self.create_text_message(error_message) 