from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class UpdateRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Update one or multiple records in a NocoDB table
        """
        # Get parameters
        table_name = tool_parameters.get("table_name", "")
        row_id = tool_parameters.get("row_id")
        data_str = tool_parameters.get("data", "")
        bulk_ids_str = tool_parameters.get("bulk_ids")
        
        # Validate required parameters
        if not table_name:
            yield self.create_text_message("Table name is required.")
            return
            
        if not data_str:
            yield self.create_text_message("Update data is required.")
            return
        
        # Parse JSON data
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            yield self.create_text_message(f"Invalid JSON data: {str(e)}")
            return
        
        if not isinstance(data, dict):
            yield self.create_text_message("Update data must be a JSON object with field values.")
            return
        
        if not data:
            yield self.create_text_message("Update data cannot be empty.")
            return
        
        # Parse bulk IDs if provided
        bulk_ids = []
        if bulk_ids_str:
            bulk_ids = [id_str.strip() for id_str in bulk_ids_str.split(",") if id_str.strip()]
        
        # Validate update operation parameters
        is_bulk = bool(bulk_ids)
        if is_bulk and row_id:
            yield self.create_text_message("Cannot specify both row_id and bulk_ids. Use row_id for single update or bulk_ids for bulk update.")
            return
        elif not is_bulk and not row_id:
            yield self.create_text_message("Either row_id (for single update) or bulk_ids (for bulk update) must be provided.")
            return
        
        # Normalize table name so first letter of each word is uppercase
        table_name = ' '.join(word.capitalize() for word in table_name.split(' '))
        
        try:
            # Get credentials
            nocodb_url = self.runtime.credentials.get("nocodb_url")
            api_token = self.runtime.credentials.get("nocodb_api_token")
            base_id = self.runtime.credentials.get("nocodb_base_id")
            
            if not nocodb_url or not api_token or not base_id:
                yield self.create_text_message("NocoDB credentials are not properly configured.")
                return
            
            # Remove trailing slash from URL if present
            if nocodb_url.endswith("/"):
                nocodb_url = nocodb_url[:-1]
            
            # Setup headers
            headers = {
                "xc-token": api_token,
                "Content-Type": "application/json"
            }
            
            # Get table ID from table name
            table_id = self._get_table_id(nocodb_url, headers, base_id, table_name)
            if not table_id:
                yield self.create_text_message(f"Table '{table_name}' not found in base '{base_id}'")
                return
            
            # Determine endpoint and payload based on operation type
            if is_bulk:
                # Bulk update endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records/bulk"
                payload = {"ids": bulk_ids, "data": data}
                record_count = len(bulk_ids)
                operation_type = "bulk"
            else:
                # Single record update endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records/{row_id}"
                payload = data
                record_count = 1
                operation_type = "single record"
            
            # Make the request
            response = requests.patch(url, headers=headers, json=payload, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                yield self.create_text_message("Authentication failed - invalid API token")
                return
            elif response.status_code == 404:
                if is_bulk:
                    yield self.create_text_message("One or more records not found for bulk update")
                else:
                    yield self.create_text_message(f"Record with ID '{row_id}' not found")
                return
            elif response.status_code == 400:
                yield self.create_text_message(f"Bad request - please check your data format and column names: {response.text}")
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Failed to update records: HTTP {response.status_code}")
                return
                
            result = response.json()
            
            # Create summary message
            summary = f"Successfully updated {record_count} record(s) in table '{table_name}' ({operation_type})"
            
            yield self.create_text_message(summary)
            yield self.create_json_message(result)
            
        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message("Failed to connect to NocoDB - please check your configuration")
        except Exception as e:
            yield self.create_text_message(f"Error updating records: {str(e)}")
    
    def _get_table_id(self, nocodb_url: str, headers: dict, base_id: str, table_name: str) -> str:
        """Get the table ID from the table name"""
        try:
            response = requests.get(
                f"{nocodb_url}/api/v2/meta/bases/{base_id}/tables",
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                return ""
            
            tables = response.json().get("list", [])
            
            # Find the table with the matching name
            for table in tables:
                if table.get("title") == table_name:
                    return table.get("id")
            
            return ""
            
        except Exception:
            return "" 