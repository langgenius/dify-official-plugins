from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetSchemaTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Retrieve the schema (columns) of a NocoDB table
        """
        # Get parameters
        table_name = tool_parameters.get("table_name", "")
        
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
            
            # Fetch table metadata using the table ID
            url = f"{nocodb_url}/api/v2/meta/tables/{table_id}"
            response = requests.get(url, headers=headers, timeout=30)
            
            # Handle response
            if response.status_code == 401:
                yield self.create_text_message("Authentication failed - invalid API token")
                return
            elif response.status_code == 404:
                yield self.create_text_message(f"Table '{table_name}' metadata not found")
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Failed to retrieve schema: HTTP {response.status_code}")
                return
                
            result = response.json()
            
            # Extract and format schema information
            columns = result.get("columns", [])
            column_count = len(columns)
            
            # Create a simplified column summary for the text message
            column_names = [col.get("title", col.get("column_name", "Unknown")) for col in columns]
            column_types = {}
            for col in columns:
                col_name = col.get("title", col.get("column_name", "Unknown"))
                col_type = col.get("uidt", col.get("dt", "Unknown"))
                if col.get("pk"):
                    col_type += " (Primary Key)"
                if col.get("rqd"):
                    col_type += " (Required)"
                column_types[col_name] = col_type
            
            # Create summary message
            summary = f"Retrieved schema for table '{table_name}' with {column_count} columns: {', '.join(column_names)}"
            
            yield self.create_text_message(summary)
            
            # Create a more readable schema summary
            schema_summary = {
                "table_name": table_name,
                "table_id": table_id,
                "column_count": column_count,
                "columns": column_types,
                "full_schema": result
            }
            
            yield self.create_json_message(schema_summary)
            
        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message("Failed to connect to NocoDB - please check your configuration")
        except Exception as e:
            yield self.create_text_message(f"Error retrieving schema: {str(e)}")
    
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