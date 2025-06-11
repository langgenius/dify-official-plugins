from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListObjectsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List objects (PDFs and images) from APITemplate.io
        """
        try:
            # Get parameters
            limit = tool_parameters.get("limit", "300").strip()
            offset = tool_parameters.get("offset", "0").strip()
            transaction_type = tool_parameters.get("transaction_type", "").strip()
            
            # Validate and convert limit
            try:
                limit_int = int(limit) if limit else 300
                if limit_int > 300:
                    limit_int = 300
            except ValueError:
                limit_int = 300
            
            # Validate and convert offset
            try:
                offset_int = int(offset) if offset else 0
            except ValueError:
                offset_int = 0
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                yield self.create_text_message("APITemplate.io API key is not configured.")
                return
            
            # Prepare API request
            headers = {
                "X-API-KEY": api_key,
                "Content-Type": "application/json"
            }
            
            # Build query parameters
            params = {
                "limit": str(limit_int),
                "offset": str(offset_int)
            }
            
            # Add transaction type filter if provided
            if transaction_type and transaction_type.upper() in ["PDF", "JPEG", "MERGE"]:
                params["transaction_type"] = transaction_type.upper()
            
            # Make API request
            response = requests.get(
                "https://rest.apitemplate.io/v2/list-objects",
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = f"API Error: {error_data['message']}"
                except:
                    error_msg = f"API request failed with status {response.status_code}: {response.text}"
                
                yield self.create_text_message(error_msg)
                return
            
            # Parse response
            result = response.json()
            
            if result.get("status") != "success":
                error_msg = result.get("message", "Unknown error occurred")
                yield self.create_text_message(f"Failed to list objects: {error_msg}")
                return
            
            # Extract data
            objects_data = result.get("data", [])
            total_count = len(objects_data)
            
            # Create summary
            summary = f"Retrieved {total_count} objects"
            if transaction_type:
                summary += f" (filtered by {transaction_type})"
            summary += f"\nOffset: {offset_int}, Limit: {limit_int}"
            
            # Count by type
            type_counts = {}
            for obj in objects_data:
                obj_type = obj.get("transaction_type", "Unknown")
                type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
            
            if type_counts:
                summary += f"\nBreakdown: {', '.join([f'{k}: {v}' for k, v in type_counts.items()])}"
            
            yield self.create_text_message(summary)
            yield self.create_json_message({
                "status": "success",
                "total_count": total_count,
                "offset": offset_int,
                "limit": limit_int,
                "filter": transaction_type if transaction_type else "none",
                "type_counts": type_counts,
                "objects": objects_data
            })
            
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 