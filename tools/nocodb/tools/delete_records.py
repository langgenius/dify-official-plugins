from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DeleteRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete one or multiple records from a NocoDB table
        """
        # Get parameters
        table_name = tool_parameters.get("table_name", "")
        row_id = tool_parameters.get("row_id")
        bulk_ids_str = tool_parameters.get("bulk_ids")
        
        # Validate required parameters
        if not table_name:
            yield self.create_text_message("Table name is required.")
            return
        
        # Parse bulk IDs if provided
        bulk_ids = []
        if bulk_ids_str:
            bulk_ids = [id_str.strip() for id_str in bulk_ids_str.split(",") if id_str.strip()]
        
        # Validate delete operation parameters
        is_bulk = bool(bulk_ids)
        if is_bulk and row_id:
            yield self.create_text_message("Cannot specify both row_id and bulk_ids. Use row_id for single deletion or bulk_ids for bulk deletion.")
            return
        elif not is_bulk and not row_id:
            yield self.create_text_message("Either row_id (for single deletion) or bulk_ids (for bulk deletion) must be provided.")
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
                # Bulk deletion endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records/bulk"
                payload = {"ids": bulk_ids}
                record_count = len(bulk_ids)
                operation_type = "bulk"
                
                # Use requests.request with DELETE method and JSON body
                response = requests.request("DELETE", url, headers=headers, json=payload, timeout=30)
            else:
                # Single record deletion endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records/{row_id}"
                record_count = 1
                operation_type = "single record"
                
                response = requests.delete(url, headers=headers, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                yield self.create_text_message("Authentication failed - invalid API token")
                return
            elif response.status_code == 404:
                if is_bulk:
                    yield self.create_text_message("One or more records not found for bulk deletion")
                else:
                    yield self.create_text_message(f"Record with ID '{row_id}' not found")
                return
            elif response.status_code not in [200, 204]:
                yield self.create_text_message(f"Failed to delete records: HTTP {response.status_code}")
                return
            
            # Handle different response formats
            if response.status_code == 204:
                # No content response
                result = {"success": True, "message": f"{record_count} record(s) deleted successfully"}
            else:
                try:
                    result = response.json()
                    # Handle different response formats from NocoDB
                    if isinstance(result, (int, float)):
                        result = {"success": True, "deleted_count": result, "message": f"{result} record(s) deleted successfully"}
                    elif not isinstance(result, dict):
                        result = {"success": True, "message": f"{record_count} record(s) deleted successfully", "response_data": result}
                except:
                    result = {"success": True, "message": f"{record_count} record(s) deleted successfully"}
            
            # Create summary message
            summary = f"Successfully deleted {record_count} record(s) from table '{table_name}' ({operation_type})"
            
            yield self.create_text_message(summary)
            yield self.create_json_message(result)
            
        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message("Failed to connect to NocoDB - please check your configuration")
        except Exception as e:
            yield self.create_text_message(f"Error deleting records: {str(e)}")
    
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