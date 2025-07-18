from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create one or multiple records in a NocoDB table
        """
        # Get parameters
        table_name = tool_parameters.get("table_name", "")
        data_str = tool_parameters.get("data", "")
        bulk = tool_parameters.get("bulk", False)
        
        # Validate required parameters
        if not table_name:
            yield self.create_text_message("Table name is required.")
            return
            
        if not data_str:
            yield self.create_text_message("Data is required for record creation.")
            return
        
        # Parse JSON data
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            yield self.create_text_message(f"Invalid JSON data: {str(e)}")
            return
        
        # Normalize table name so first letter of each word is uppercase
        table_name = ' '.join(word.capitalize() for word in table_name.split(' '))
        
        # Validate data structure
        if bulk:
            if not isinstance(data, list):
                yield self.create_text_message("For bulk creation, data must be a list of record objects.")
                return
            if not data:
                yield self.create_text_message("Data list cannot be empty for bulk creation.")
                return
        else:
            if isinstance(data, list):
                if len(data) > 1:
                    yield self.create_text_message("For single record creation, provide a single object, not a list. Set bulk=true for multiple records.")
                    return
                data = data[0] if data else {}
            if not isinstance(data, dict):
                yield self.create_text_message("For single record creation, data must be a JSON object with field values.")
                return
            if not data:
                yield self.create_text_message("Data object cannot be empty for record creation.")
                return
        
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
            
            # Determine endpoint based on bulk operation
            if bulk:
                # Bulk creation endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records/bulk"
                record_count = len(data)
                operation_type = "bulk"
            else:
                # Single record creation endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records"
                record_count = 1
                operation_type = "single record"
            
            # Make the request
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                yield self.create_text_message("Authentication failed - invalid API token")
                return
            elif response.status_code == 400:
                yield self.create_text_message(f"Bad request - please check your data format and column names: {response.text}")
                return
            elif response.status_code not in [200, 201]:
                yield self.create_text_message(f"Failed to create records: HTTP {response.status_code}")
                return
                
            result = response.json()
            
            # Create summary message
            summary = f"Successfully created {record_count} record(s) in table '{table_name}' ({operation_type})"
            
            yield self.create_text_message(summary)
            yield self.create_json_message(result)
            
        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message("Failed to connect to NocoDB - please check your configuration")
        except Exception as e:
            yield self.create_text_message(f"Error creating records: {str(e)}")
    
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