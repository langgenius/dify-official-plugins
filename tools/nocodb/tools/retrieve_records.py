from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class RetrieveRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Retrieve one or multiple records from a NocoDB table
        """
        # Get parameters
        table_name = tool_parameters.get("table_name", "")
        row_id = tool_parameters.get("row_id")
        filters = tool_parameters.get("filters")
        limit = tool_parameters.get("limit", 10)
        offset = tool_parameters.get("offset", 0)
        sort = tool_parameters.get("sort")
        fields = tool_parameters.get("fields")
        
        # Validate required parameters
        if not table_name:
            yield self.create_text_message("Table name is required.")
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
            
            # Determine endpoint and parameters based on whether we're fetching single or multiple records
            if row_id:
                # Single record endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records/{row_id}"
                response = requests.get(url, headers=headers, timeout=30)
                
                if response.status_code == 404:
                    yield self.create_text_message(f"Record with ID '{row_id}' not found")
                    return
                    
            else:
                # Multiple records endpoint
                url = f"{nocodb_url}/api/v2/tables/{table_id}/records"
                
                # Build query parameters
                params = {}
                if limit is not None:
                    params["limit"] = limit
                if offset is not None:
                    params["offset"] = offset
                if sort:
                    params["sort"] = sort
                if fields:
                    params["fields"] = fields
                if filters:
                    params["where"] = filters
                
                response = requests.get(url, headers=headers, params=params, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                yield self.create_text_message("Authentication failed - invalid API token")
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Failed to retrieve records: HTTP {response.status_code}")
                return
                
            result = response.json()
            
            # Create summary message
            if row_id:
                record_count = 1 if result and not result.get("error") else 0
                summary = f"Retrieved {record_count} record from table '{table_name}'"
            else:
                records = result.get("list", [])
                record_count = len(records)
                summary = f"Retrieved {record_count} records from table '{table_name}'"
                
                if limit and record_count == limit:
                    summary += f" (limited to {limit})"
                
                if "pageInfo" in result:
                    page_info = result.get("pageInfo", {})
                    if page_info.get("totalRows"):
                        summary += f" of {page_info.get('totalRows')} total rows"
            
            yield self.create_text_message(summary)
            yield self.create_json_message(result)
            
        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message("Failed to connect to NocoDB - please check your configuration")
        except Exception as e:
            yield self.create_text_message(f"Error retrieving records: {str(e)}")
    
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